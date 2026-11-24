"""Bootstrap fresh targets, fail during projection, resume, then replay without duplicates."""

import hashlib
import json
import uuid

import psycopg2
import pytest
from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.buckets import projection
from app.buckets.db import one, shutdown, transaction
from app.core.config import settings
from app.services import neo4j
from app.services.allocation import canonical
from app.services.mongo import get_database
from scripts.bucket_setup import setup
from seeding import load
from seeding.generate import generate

pytestmark = pytest.mark.skipif(not settings.BUCKET_MODE, reason="Requires isolated bucket stack")


def test_fresh_seed_failure_resume_and_replay(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    saved = {
        name: getattr(settings, name)
        for name in ("DATABASE_URL", "BUCKET_SITE_URLS", "BUCKET_DATASET", "MONGO_DB", "GRAPH_GENERATION")
    }
    root = make_url(settings.DATABASE_URL)
    names = {kind: f"bucket_fresh_{suffix}_{kind}" for kind in ("core", "a", "b")}
    admin = psycopg2.connect(**settings.database_connect_args)
    admin.autocommit = True
    with admin.cursor() as cursor:
        for name in names.values():
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    admin.close()
    shutdown()
    try:
        settings.DATABASE_URL = root.set(database=names["core"]).render_as_string(hide_password=False)
        settings.BUCKET_SITE_URLS = json.dumps(
            {
                site: root.set(database=names[kind], drivername="postgresql").render_as_string(hide_password=False)
                for site, kind in [("A", "a"), ("B", "b")]
            }
        )
        settings.BUCKET_DATASET = f"contract-trial-{suffix}"
        settings.MONGO_DB = f"bucket_fresh_{suffix}"
        settings.GRAPH_GENERATION = 1
        setup()
        neo4j.initialize()

        def isolated_profile(profile, scale=1):
            data = generate(profile, scale)
            data["config"]["dataset_id"] = settings.BUCKET_DATASET
            data.pop("digest")
            data["digest"] = hashlib.sha256(canonical(data).encode()).hexdigest()
            return data

        monkeypatch.setattr(load, "generate", isolated_profile)
        document = load.plan("contract-small")
        original = projection.backfill

        def fail(**kwargs):
            raise RuntimeError("Injected projection outage")

        monkeypatch.setattr(projection, "backfill", fail)
        with pytest.raises(RuntimeError):
            load.apply(document)
        with transaction() as core:
            assert one(core, "SELECT state FROM seed_runs")["state"] == "failed"
        monkeypatch.setattr(projection, "backfill", original)
        first = load.apply(document)
        assert first["verification"]["ok"]
        assert first["counts"]["products"] == 24
        metadata = get_database().product_details.find_one({"image_metadata.0": {"$exists": True}})
        from app.schemas.catalog import ImageMetadataInput
        from app.services.image_metadata import replace

        image_id = metadata["image_metadata"][0]["image_id"]
        replace(metadata["product_id"], [ImageMetadataInput(image_id=image_id, caption="User text preserved")])
        second = load.apply(document)
        assert first["run_id"] == second["run_id"]
        assert first["verification"]["id_checksum"] == second["verification"]["id_checksum"]
        assert (
            get_database().product_details.find_one({"product_id": metadata["product_id"]})["image_metadata"][0][
                "caption"
            ]
            == "User text preserved"
        )
        with transaction() as core:
            assert one(core, "SELECT count(*) AS n FROM seed_manifest")["n"] == 1
    finally:
        shutdown()
        for name, value in saved.items():
            setattr(settings, name, value)
