"""Opt-in real DB tests; only UUID databases created here are written/dropped.

INDEX_CONFIG_INTEGRATION=1 INDEX_TEST_PG_DSN=postgresql://.../postgres
INDEX_TEST_MONGO_URI=mongodb://... pytest --noconftest tests/test_index_config_integration.py
"""

import hashlib
import json
import os
import shutil
import uuid
from contextlib import closing
from datetime import UTC, datetime

import pytest

from app.services.index_config import DATABASE_DIR, IndexCatalog, load_catalog
from app.services.index_mongo import applied_mongo_catalog, apply_mongo, plan_mongo
from app.services.index_postgres import plan_postgres
from app.services.index_releases import release_catalog
from scripts.generate_index_migration import generate

pytestmark = pytest.mark.skipif(os.getenv("INDEX_CONFIG_INTEGRATION") != "1", reason="Explicit disposable DB opt-in")


@pytest.fixture
def postgres(monkeypatch):
    import psycopg2
    from psycopg2 import sql
    from sqlalchemy.engine import make_url

    from app.core.config import settings
    from scripts.init_db import load_schema
    from scripts.migrate import connect, run_migrations

    dsn = os.environ["INDEX_TEST_PG_DSN"]
    name = "index_config_test_" + uuid.uuid4().hex[:12]
    with closing(psycopg2.connect(dsn)) as administration:
        administration.autocommit = True
        with administration.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        url = make_url(dsn).set(drivername="postgresql+psycopg2", database=name)
        monkeypatch.setattr(settings, "DATABASE_URL", url.render_as_string(hide_password=False))
        monkeypatch.setattr(settings, "DB_NAME", name)
        load_schema()
        assert run_migrations() == ["001", "002", "003", "004", "005", "006", "007"]
        with closing(connect()) as connection:
            yield connection
    finally:
        with closing(psycopg2.connect(dsn)) as administration:
            administration.autocommit = True
            with administration.cursor() as cursor:
                cursor.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_postgres_parity_generation_upgrade_rollback_and_applied_snapshot(postgres, tmp_path, monkeypatch):
    from scripts import migrate
    from scripts.verify_indexing_v2 import verify

    catalog = load_catalog()
    from scripts.indexes import execute

    # Applied verification must not parse an unfinished/invalid desired catalog.
    invalid_desired = tmp_path / "unfinished.json"
    invalid_desired.write_text("{")
    assert execute("verify", "postgresql", invalid_desired)["result"] == "PASS"
    root = tmp_path / "database"
    shutil.copytree(DATABASE_DIR / "indexing", root / "indexing")
    shutil.copytree(DATABASE_DIR / "04_migrations", root / "04_migrations")
    monkeypatch.setattr(migrate, "DATABASE_DIR", root)
    plan = plan_postgres(postgres, catalog)
    assert all(i["status"] == "matched" for i in plan["indexes"])
    assert generate(postgres, catalog, root)["generated"] is False
    assert verify()["result"] == "PASS"  # historical 007 verifier still works
    checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "04_migrations").glob("*.sql")}
    payload = catalog.payload()
    payload["revision"] = "index-v2-test"
    payload["postgresql"].append(
        {
            "schema": "public",
            "table": "product",
            "name": "idx_json_demo_price",
            "keys": [{"column": "price", "order": "DESC"}, {"column": "product_id"}],
            "predicate": {"column": "is_deleted", "op": "eq", "value": False},
        }
    )
    desired = IndexCatalog.model_validate(payload)
    before = plan_postgres(postgres, desired)
    assert before["indexes"][-1]["status"] == "missing"
    assert release_catalog(postgres, root).revision == "index-v1"
    generated = generate(postgres, desired, root)
    assert generated["migration"].startswith("008_")
    assert '"price" DESC NULLS FIRST' in (root / "04_migrations" / generated["migration"]).read_text()
    assert migrate.run_migrations() == ["008"]
    assert migrate.run_migrations() == []
    assert release_catalog(postgres, root).revision == "index-v2-test"
    assert all(i["status"] == "matched" for i in plan_postgres(postgres, desired)["indexes"])
    assert generate(postgres, desired, root)["generated"] is False
    for name, digest in checksums.items():
        assert hashlib.sha256((root / "04_migrations" / name).read_bytes()).hexdigest() == digest

    # Changed direction and nonexistent predicate columns are conflicts, not false matches.
    modified = desired.payload()
    modified["postgresql"][-1]["keys"][0]["order"] = "ASC"
    assert plan_postgres(postgres, IndexCatalog.model_validate(modified))["indexes"][-1]["status"] == "conflict"
    modified = desired.payload()
    modified["postgresql"][-1]["predicate"]["column"] = "typo_column"
    assert plan_postgres(postgres, IndexCatalog.model_validate(modified))["indexes"][-1]["status"] == "conflict"

    # Runner rollback includes DDL and history row when later SQL fails.
    bad = root / "04_migrations/009_test_rollback.sql"
    bad.write_text("CREATE INDEX idx_must_rollback ON product(price); SELECT 1/0;")
    with pytest.raises(Exception, match="division by zero"):
        migrate.run_migrations()
    with postgres.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('idx_must_rollback'),(SELECT count(*) FROM schema_migrations WHERE version='009')"
        )
        assert cursor.fetchone() == (None, 0)
    bad.unlink()

    # Missing attached partition indexes must be detected even with a valid named parent.
    from app.services.index_postgres import differences, inventory

    rows, _, _ = inventory(postgres)
    target = next(i for i in catalog.postgresql if i.name == "idx_order_voucher_lookup")
    parent = next(r for r in rows if r["name"] == target.name)
    children = [r for r in rows if r["parent"] == parent["oid"]]
    assert len(children) == 4 and all(not differences(target, child) for child in children)
    snapshot = root / "indexing/snapshots/index-v2-test.json"
    state = json.loads(snapshot.read_text())
    state["postgresql"][-1]["unique"] = True
    snapshot.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="checksum"):
        migrate.run_migrations()


def test_mongo_parity_idempotence_constraints_conflicts_and_applied_state(tmp_path):
    import subprocess
    import sys

    from pymongo import MongoClient
    from pymongo.errors import DuplicateKeyError

    from app.services.mongo_schema import validators
    from scripts.init_mongo import initialize

    client = MongoClient(os.environ["INDEX_TEST_MONGO_URI"], serverSelectionTimeoutMS=3000)
    name = "index_config_test_" + uuid.uuid4().hex[:12]
    database = client[name]
    catalog = load_catalog()
    try:
        result = initialize(database, catalog)
        assert len(result["indexes"]["created"]) == 18  # ETL initializes its own index first.
        before = {c: database[c].index_information() for c in database.list_collection_names()}
        assert initialize(database, catalog)["indexes"]["created"] == []
        assert before == {c: database[c].index_information() for c in database.list_collection_names()}
        assert all(i["status"] == "matched" for i in plan_mongo(database, catalog)["indexes"])
        assert applied_mongo_catalog(database).revision == catalog.revision
        independent_verify = subprocess.run(
            [sys.executable, "-m", "scripts.verify_indexes", "--engine", "mongodb"],
            env={
                **os.environ,
                "DATABASE_SRC": str(tmp_path / "without-desired-catalog"),
                "MONGO_URI": os.environ["INDEX_TEST_MONGO_URI"],
                "MONGO_DB": name,
            },
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(independent_verify.stdout)["result"] == "PASS"
        assert database.system_logs.index_information()["created_at_1"]["expireAfterSeconds"] == 7776000
        assert database.product_details.index_information()["description_text_tags_text"]["weights"] == {
            "description": 1,
            "tags": 1,
        }
        assert (
            database.command("listCollections", filter={"name": "product_details"})["cursor"]["firstBatch"][0][
                "options"
            ]["validator"]
            == validators()["product_details"]
        )

        document = {
            "_id": "json-test-1",
            "schema_version": 1,
            "product_id": 1,
            "category_id": 1,
            "attributes": {"brand": "demo"},
            "updated_at": datetime.now(UTC),
        }
        database.product_details.insert_one(document)
        with pytest.raises(DuplicateKeyError):
            database.product_details.insert_one({**document, "_id": "json-test-duplicate"})

        # New JSON index really reaches the server and the applied snapshot remains separate.
        payload = catalog.payload()
        payload["revision"] = "mongo-v2-test"
        payload["mongodb"].append(
            {
                "collection": "product_details",
                "keys": [["attributes.color", 1]],
                "options": {"name": "idx_json_color", "sparse": True},
            }
        )
        desired = IndexCatalog.model_validate(payload)
        assert plan_mongo(database, desired)["indexes"][-1]["status"] == "missing"
        assert applied_mongo_catalog(database).revision == "index-v1"
        assert len(apply_mongo(database, desired)["created"]) == 1
        assert database.product_details.index_information()["idx_json_color"]["sparse"] is True
        assert applied_mongo_catalog(database).revision == "mongo-v2-test"

        changed = desired.payload()
        ttl = next(i for i in changed["mongodb"] if "expireAfterSeconds" in i["options"])
        ttl["options"]["expireAfterSeconds"] = 10
        conflict = IndexCatalog.model_validate(changed)
        assert any(
            i["status"] == "conflict" and "ttl" in i["reasons"] for i in plan_mongo(database, conflict)["indexes"]
        )
        with pytest.raises(ValueError, match="conflict"):
            apply_mongo(database, conflict)
        assert database.system_logs.index_information()["created_at_1"]["expireAfterSeconds"] == 7776000

        # Removal leaves the physical index for explicit lifecycle review.
        removed = desired.payload()
        removed["mongodb"].pop()
        removal = IndexCatalog.model_validate(removed)
        result = apply_mongo(database, removal)
        assert any(i["name"] == "idx_json_color" for i in result["unmanaged"])
        assert "idx_json_color" in database.product_details.index_information()
    finally:
        client.drop_database(name)
        client.close()
