"""Preserve IDs, metadata and source data in a real import to new trial databases."""

import json
import uuid

import psycopg2
import pytest
from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.buckets.db import one, shutdown, transaction
from app.core.config import settings
from app.services.mongo import get_database
from scripts.bucket_schema import DATABASE
from scripts.bucket_setup import setup
from scripts.migrate_catalogue_to_buckets import finish_import, import_snapshot, inventory

pytestmark = pytest.mark.skipif(not settings.BUCKET_MODE, reason="Requires isolated bucket stack")


def test_legacy_import_preserves_source_ids_and_metadata(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    saved = {
        name: getattr(settings, name)
        for name in ("DATABASE_URL", "BUCKET_SITE_URLS", "BUCKET_DATASET", "MONGO_DB", "GRAPH_ENABLED")
    }
    root = make_url(settings.DATABASE_URL)
    names = {kind: f"bucket_import_{suffix}_{kind}" for kind in ("source", "core", "a", "b")}
    admin = psycopg2.connect(**settings.database_connect_args)
    admin.autocommit = True
    with admin.cursor() as cursor:
        for name in names.values():
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    admin.close()
    urls = {kind: root.set(database=name).render_as_string(hide_password=False) for kind, name in names.items()}
    source = psycopg2.connect(urls["source"].replace("postgresql+psycopg2://", "postgresql://"))
    files = [
        DATABASE / line[3:].strip()
        for line in (DATABASE / "init.sql").read_text().splitlines()
        if line.startswith("\\i ") and not line[3:].startswith("03_seeds/")
    ]
    files += sorted((DATABASE / "04_migrations").glob("[0-9][0-9][0-9]_*.sql"))
    with source, source.cursor() as cursor:
        cursor.execute("\n".join(path.read_text() for path in files))
        cursor.execute("SET LOCAL timezone='UTC'")
        cursor.execute("INSERT INTO role(role_id,role_name) VALUES(3,'User')")
        for identifier in (1, 2):
            cursor.execute(
                "INSERT INTO user_core(user_id,username,email) VALUES(%s,%s,%s)",
                (identifier, f"legacy{identifier}", f"legacy{identifier}@example.com"),
            )
            cursor.execute("INSERT INTO user_profile(user_id,full_name) VALUES(%s,'Legacy user')", (identifier,))
            cursor.execute(
                "INSERT INTO user_secret(user_id,password_hash,random_key) VALUES(%s,'!disabled',%s)",
                (identifier, f"key-{identifier}"),
            )
            cursor.execute("INSERT INTO user_wallet(user_id,balance) VALUES(%s,1000000)", (identifier,))
            cursor.execute("INSERT INTO user_role VALUES(%s,3)", (identifier,))
        cursor.execute("INSERT INTO category(category_id,name) VALUES(1,'Legacy category')")
        cursor.execute(
            "INSERT INTO product(product_id,seller_id,category_id,title,price,quantity,status) "
            "VALUES(41,1,1,'Legacy item',100000,2,1)"
        )
        asset = sorted((DATABASE / "03_seeds/media/products").glob("*.jpg"))[0].name
        cursor.execute(
            "INSERT INTO product_image(image_id,product_id,image_url) VALUES(51,41,%s)", (f"/media/products/{asset}",)
        )
    source.close()
    mongo_source = f"bucket_import_source_{suffix}"
    get_database().client[mongo_source].product_details.insert_one(
        {
            "product_id": 41,
            "attributes": {"note": "keep"},
            "image_metadata": [{"image_id": 51, "caption": "Ghi chú được giữ nguyên", "description": "Metadata nguồn"}],
            "metadata_revision": 7,
        }
    )
    monkeypatch.setenv("BUCKET_LEGACY_URL", urls["source"].replace("postgresql+psycopg2://", "postgresql://"))
    monkeypatch.setenv("BUCKET_LEGACY_MONGO_URI", settings.MONGO_URI)
    monkeypatch.setenv("BUCKET_LEGACY_MONGO_DB", mongo_source)
    monkeypatch.setenv("BUCKET_LEGACY_MEDIA_DIR", str(DATABASE / "03_seeds/media"))
    snapshot = inventory("UTC")
    assert not snapshot["violations"]
    shutdown()
    try:
        settings.DATABASE_URL = urls["core"]
        settings.BUCKET_SITE_URLS = json.dumps(
            {
                sid: urls[kind].replace("postgresql+psycopg2://", "postgresql://")
                for sid, kind in [("A", "a"), ("B", "b")]
            }
        )
        settings.BUCKET_DATASET = f"migration-trial-{suffix}"
        settings.MONGO_DB = f"bucket_import_target_{suffix}"
        settings.GRAPH_ENABLED = False
        setup()
        assert import_snapshot(snapshot)["products"] == 1
        finish_import(snapshot)
        # Replay the same import, preserving identifiers and annotation revision.
        assert import_snapshot(snapshot)["products"] == 1
        finish_import(snapshot)
        with transaction() as core:
            assert one(core, "SELECT product_id FROM catalogue_directory")["product_id"] == 41
        metadata = get_database().product_details.find_one({"product_id": 41})
        assert metadata["image_metadata"][0]["image_id"] == 51
        assert metadata["image_metadata"][0]["caption"] == "Ghi chú được giữ nguyên"
        assert metadata["attributes"] == {"note": "keep"}
        assert inventory("UTC")["source_hash"] == snapshot["source_hash"]
    finally:
        shutdown()
        for name, value in saved.items():
            setattr(settings, name, value)
