"""Run with --noconftest. Real tests opt in via FRAGMENT_TEST_PG_DSN (trust-auth lab)."""

import json
import os

import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.catalogue_gateway import create_app
from app.services.fragment_router import FragmentContract, load_contract
from scripts.fragmentation_lab import disposable_lab


def test_contract_rejects_incomplete_ambiguous_and_executable_metadata(tmp_path):
    original = load_contract().model_dump()
    for change in (
        {"sites": [{"site_id": "A", "id_remainder": 1}]},
        {"sites": [{"site_id": "A", "id_remainder": 1}, {"site_id": "B", "id_remainder": 1}]},
        {"schema_version": 2},
        {"dsn": "secret"},
        {"primary": {**original["primary"], "relation": "product;DROP TABLE product"}},
    ):
        with pytest.raises(ValueError):
            FragmentContract.model_validate({**original, **change})
    path = tmp_path / "contract.json"
    path.write_text(json.dumps({**original, "schema_version": True}))
    with pytest.raises(ValueError):
        load_contract(path)
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="Duplicate"):
        load_contract(path)


def test_product_routing_and_fail_closed_identity():
    contract = load_contract()
    assert [contract.product_site(i) for i in (1, 2, 2147483647)] == ["A", "B", "A"]
    for invalid in (0, -1, True, 2147483648):
        with pytest.raises(ValueError):
            contract.product_site(invalid)
    state = {
        "site_id": "A",
        "id_remainder": 1,
        "contract_sha256": contract.digest(),
        "revision": contract.revision,
        "rules_valid": True,
        "reference_sha256": "ref",
    }
    contract.validate_state(state, "A")
    for change in ({"site_id": "B"}, {"rules_valid": False}, {"contract_sha256": "old"}, {"reference_sha256": ""}):
        with pytest.raises(ValueError):
            contract.validate_state({**state, **change}, "A")


@pytest.fixture(scope="module")
def lab():
    dsn = os.getenv("FRAGMENT_TEST_PG_DSN")
    if not dsn:
        pytest.skip("Requires an explicitly selected disposable PostgreSQL lab server")
    with disposable_lab(dsn) as instance:
        yield instance


@pytest.fixture
def client(lab):
    with TestClient(create_app(lab.dsn("A", "global_reader"), site_b_url=lab.dsn("B", "global_reader"))) as c:
        yield c


def test_gateway_global_pagination_filter_and_images(client):
    assert client.get("/ready").status_code == 200
    body = client.get("/products?limit=100").json()
    assert body["total"] == 6 and body["complete"] and body["sites"] == ["A", "B"]
    assert [p["product_id"] for p in body["items"]] == [1, 2, 3, 4, 9, 10]
    paged = [
        p["product_id"] for offset in (0, 2, 4) for p in client.get(f"/products?skip={offset}&limit=2").json()["items"]
    ]
    assert paged == [1, 2, 3, 4, 9, 10]
    assert client.get("/products?category_id=2").json()["total"] == 2
    assert client.get("/products?search=%27%3BSELECT%201%3B--").json()["total"] == 0
    assert len(client.get("/products/4").json()["product_images"]) == 4
    assert client.get("/products/2").json()["product_images"] == []
    assert client.get("/products?seller_id=105").json()["total"] == 0
    assert client.get("/products?seller_id=999999").status_code == 404
    for identifier in (5, 6, 7, 8, 999999):
        assert client.get(f"/products/{identifier}").status_code == 404
    for path in ("/products/0", "/products/-1", "/products/2147483648", "/products?seller_id=0"):
        assert client.get(path).status_code == 422
    assert client.post("/products", json={}).status_code == 405


@pytest.mark.parametrize("down,available,missing", [("B", 1, 2), ("A", 2, 1)])
def test_product_only_contacts_owner_and_survives_other_site_outage(lab, client, monkeypatch, down, available, missing):
    original = psycopg2.connect
    contacted = []

    def connect(dsn, **kwargs):
        contacted.append(dsn)
        if lab.names[down] in dsn:
            raise psycopg2.OperationalError("simulated site outage")
        return original(dsn, **kwargs)

    monkeypatch.setattr(psycopg2, "connect", connect)
    assert client.get(f"/products/{available}").status_code == 200
    assert len(contacted) == 1 and lab.names[down] not in contacted[0]
    assert client.get(f"/products/{missing}").status_code == 503
    if down == "A":
        assert client.get("/ready").status_code == 503
    # Global FDW health at A needs B too. A failed connect is checked above;
    # real B unavailability is additionally tested by an invalid FDW endpoint below.
    if down == "A":
        assert client.get("/products").status_code == 503


def test_seller_routing_contacts_only_relevant_data_and_legacy_fallback(lab, client, monkeypatch):
    contacted = []
    original = psycopg2.connect

    def connect(dsn, **kwargs):
        contacted.append(dsn)
        return original(dsn, **kwargs)

    monkeypatch.setattr(psycopg2, "connect", connect)
    result = client.get("/products?seller_id=101").json()
    assert result["sites"] == ["A"] and all(p["seller_id"] == 101 for p in result["items"])
    assert all(lab.names["A"] in dsn for dsn in contacted)
    assert client.get("/products?seller_id=202").json()["sites"] == ["B"]
    with TestClient(create_app(lab.dsn("A", "global_reader"), site_b_url="")) as fdw:
        assert fdw.get("/products/4").status_code == 200
    with TestClient(create_app(lab.dsn("A", "global_reader"), routed=False)) as legacy:
        assert legacy.get("/products/4").status_code == 200


def test_actual_remote_failure_and_recovery(lab, client):
    lab.sql("A", "ALTER SERVER server_b OPTIONS(SET port '1')")
    try:
        assert client.get("/products").status_code == 503
        assert client.get("/ready").status_code == 503
        assert client.get("/products/1").status_code == 200
        assert client.get("/products/2").status_code == 200  # direct B bypasses FDW
    finally:
        from psycopg2.extensions import parse_dsn

        port = parse_dsn(lab.base_dsn).get("port", "5432")
        lab.sql("A", f"ALTER SERVER server_b OPTIONS(SET port '{port}')")
    assert client.get("/ready").status_code == 200


def test_schema_reference_drift_is_rejected_then_recovers(lab, client):
    for mutation, restore in (
        (
            "ALTER TABLE product DISABLE TRIGGER enforce_product_site",
            "ALTER TABLE product ENABLE TRIGGER enforce_product_site",
        ),
        (
            "UPDATE category SET name='drift' WHERE category_id=1",
            "UPDATE category SET name='Electronics' WHERE category_id=1",
        ),
    ):
        lab.sql("B", mutation)
        try:
            assert client.get("/products/2").status_code == 503
            assert client.get("/products").status_code == 503
            assert client.get("/products/1").status_code == 200
        finally:
            lab.sql("B", restore)
    assert client.get("/ready").status_code == 200


def test_site_upgrade_idempotence_checksum_and_constraint_rollback(lab, tmp_path):
    import sites

    assert all(not v["pending"] for v in lab.upgrade(apply=False)["sites"].values())
    assert all(not v["pending"] for v in lab.upgrade()["sites"].values())
    for statement in (
        "UPDATE product SET seller_id=103 WHERE product_id=1",
        "INSERT INTO product_image(product_id,image_url) VALUES(2,'/remote')",
        "INSERT INTO product(product_id,seller_id,category_id,title,price,quantity) VALUES(100002,101,1,'bad',1,1)",
    ):
        with pytest.raises(psycopg2.IntegrityError):
            lab.sql("A", statement)
    old = sites.SQL_DIR
    (tmp_path / "migrations").mkdir()
    for p in (old / "migrations").glob("*.sql"):
        (tmp_path / "migrations" / p.name).write_text(p.read_text() + "\n-- drift")
    with pytest.raises(ValueError, match="checksum"):
        lab.upgrade(migration_dir=tmp_path / "migrations")


def test_full_row_audit_and_missing_vertical_fragment(lab):
    from contextlib import ExitStack, closing

    from scripts.verify_fragmentation import audit, read

    with ExitStack() as stack:
        connections = {s: stack.enter_context(closing(psycopg2.connect(lab.dsn(s)))) for s in "AB"}
        reference = {
            t: [r for s in "AB" for r in read(connections[s], f"SELECT * FROM {t}")]
            for t in ("product", "product_image")
        }
        assert audit(connections, reference)["result"] == "PASS"
        reference["product"] = reference["product"][1:]
        report = audit(connections, reference)
        assert report["result"] == "FAIL" and not report["checks"]["product_independent_completeness"]
        for connection in connections.values():
            connection.rollback()
        with connections["B"].cursor() as cursor:
            cursor.execute("DELETE FROM user_profile WHERE user_id=206")
        assert audit(connections)["checks"]["B_vertical_rows"] is False
        connections["B"].rollback()


def test_scoped_indexes_keep_per_site_failures_and_unique_pg_preflight(lab, monkeypatch):
    from contextlib import closing

    from app.services.index_config import IndexCatalog, load_catalog
    from app.services.index_postgres import plan_postgres
    from scripts.plan_scoped_indexes import plan_scopes

    monkeypatch.setenv("TEST_SCOPE_A", lab.dsn("A"))
    monkeypatch.setenv("TEST_SCOPE_B", lab.dsn("B"))
    scopes = {
        "site-a": {"tables": ["product", "product_image"], "dsn_env": "TEST_SCOPE_A"},
        "site-b": {"tables": ["product", "product_image"], "dsn_env": "TEST_SCOPE_B"},
    }
    assert plan_scopes(load_catalog(), scopes, verify=True)["result"] == "PASS"
    definition = lab.query("B", "SELECT pg_get_indexdef('idx_product_visible_date_id'::regclass) AS ddl")[0]["ddl"]
    lab.sql("B", "DROP INDEX idx_product_visible_date_id")
    try:
        report = plan_scopes(load_catalog(), scopes, verify=True)
        assert report["scopes"]["site-a"]["result"] == "PASS"
        assert report["scopes"]["site-b"]["result"] == "FAIL"
    finally:
        lab.sql("B", definition)
    candidate = IndexCatalog.model_validate(
        {
            "schema_version": 1,
            "revision": "unique-preflight",
            "mongodb": [],
            "postgresql": [
                {
                    "name": "candidate_unique_seller",
                    "table": "product",
                    "unique": True,
                    "keys": [{"column": "seller_id"}],
                }
            ],
        }
    )
    with closing(psycopg2.connect(lab.dsn("A"))) as connection:
        connection.set_session(readonly=True)
        plan = plan_postgres(connection, candidate)
        assert plan["indexes"][0]["status"] == "conflict"
        assert "unique_duplicate_keys" in plan["indexes"][0]["reasons"]


def test_mongo_unique_preflight_missing_null_sparse_partial_and_multikey():
    import uuid

    from pymongo import MongoClient
    from pymongo.errors import DuplicateKeyError

    from app.services.index_config import IndexCatalog
    from app.services.index_mongo import apply_mongo, plan_mongo

    uri = os.getenv("FRAGMENT_TEST_MONGO_URI")
    if not uri:
        pytest.skip("Requires disposable Mongo opt-in")
    with MongoClient(uri, serverSelectionTimeoutMS=3000) as client:
        name = "fragment_unique_test_" + uuid.uuid4().hex
        database = client[name]
        try:

            def catalog(**options):
                return IndexCatalog.model_validate(
                    {
                        "schema_version": 1,
                        "revision": "test",
                        "postgresql": [],
                        "mongodb": [
                            {
                                "collection": "reviews",
                                "keys": [["review_id", 1]],
                                "options": {"name": "candidate_unique", "unique": True, **options},
                            }
                        ],
                    }
                )

            database.reviews.insert_many([{"review_id": None}, {}])
            assert plan_mongo(database, catalog())["indexes"][0]["reasons"] == ["unique_duplicate_or_null_keys"]
            with pytest.raises(ValueError, match="conflict"):
                apply_mongo(database, catalog(), record=False)
            assert database.reviews.count_documents({}) == 2
            assert apply_mongo(database, catalog(sparse=True), record=False)["created"]
            database.reviews.drop()
            database.reviews.insert_many(
                [{}, {}, {"review_id": 1, "deleted": False}, {"review_id": 1, "deleted": True}]
            )
            partial = catalog(partialFilterExpression={"deleted": False})
            assert apply_mongo(database, partial, record=False)["created"]
            with pytest.raises(DuplicateKeyError):
                database.reviews.insert_one({"review_id": 1, "deleted": False})
            assert apply_mongo(database, partial, record=False)["created"] == []
            database.reviews.drop()
            database.reviews.insert_one({"review_id": [1, 2]})
            assert plan_mongo(database, catalog())["indexes"][0]["reasons"] == [
                "unique_multikey_requires_explicit_data_review"
            ]
        finally:
            client.drop_database(name)


def test_existing_007_sites_upgrade_without_reseed_and_reject_failed_migration(tmp_path):

    from scripts.fragmentation_lab import Lab

    dsn = os.getenv("FRAGMENT_TEST_PG_DSN")
    if not dsn:
        pytest.skip("Requires disposable PostgreSQL lab opt-in")
    lab = Lab(dsn, max_version="007")
    try:
        lab.initialize()
        for site in "AB":
            assert lab.query(site, "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1") == [
                {"version": "008"}
            ]
            assert lab.query(site, "SELECT count(*) AS n FROM product") == [{"n": 5}]
            assert lab.query(site, "SELECT count(*) AS n FROM site_schema_migrations") == [{"n": 1}]
        assert all(not v["common_pending"] for v in lab.upgrade(apply=False)["sites"].values())
        from scripts.fragmentation_lab import SQL_DIR

        for path in (SQL_DIR / "migrations").glob("*.sql"):
            (tmp_path / path.name).write_bytes(path.read_bytes())
        (tmp_path / "002_failure.sql").write_text("CREATE TABLE fragment_must_rollback(id int); SELECT 1/0;")
        with pytest.raises(psycopg2.errors.DivisionByZero):
            lab.upgrade(migration_dir=tmp_path)
        for site in "AB":
            assert lab.query(site, "SELECT to_regclass('fragment_must_rollback')::text AS name") == [{"name": None}]
            assert lab.query(site, "SELECT count(*) AS n FROM site_schema_migrations") == [{"n": 1}]
    finally:
        lab.cleanup()
