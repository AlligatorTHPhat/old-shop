"""Contract/compiler tests run without a database or application startup."""

import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.services.index_config import CATALOG_PATH, IndexCatalog, load_catalog, mongo_indexes
from app.services.index_mongo import apply_mongo, document_field, plan_mongo, signature
from app.services.index_postgres import create_sql, expression_tree, literal
from app.services.index_releases import validate_migration_snapshot
from scripts.generate_index_migration import require_additive
from scripts.indexes import execute


@pytest.fixture
def payload():
    return json.loads(CATALOG_PATH.read_text())


def test_initial_inventory_and_compatibility_adapter():
    catalog = load_catalog()
    assert len(catalog.postgresql) == 98
    assert sum(i.managed_by == "constraint" for i in catalog.postgresql) == 37
    assert len(catalog.mongodb) == 19
    indexes = mongo_indexes(catalog)
    assert indexes["reviews"][1] == ([("product_id", 1), ("created_at", -1)], {"name": "product_id_1_created_at_-1"})
    assert indexes["etl_errors"][0][0] == [("resolved", 1), ("last_at", 1)]
    assert execute("validate")["result"] == "PASS"


def test_editor_schema_is_generated_from_the_runtime_contract():
    assert json.loads((CATALOG_PATH.parent / "catalog.schema.json").read_text()) == IndexCatalog.model_json_schema(
        by_alias=True
    )


def test_database_src_resolves_packaged_catalog_and_snapshot(tmp_path):
    packaged = tmp_path / "opt/database"
    shutil.copytree(CATALOG_PATH.parent, packaged / "indexing")
    code = (
        "from app.services.index_config import load_catalog, DATABASE_DIR; "
        "c=load_catalog(); s=load_catalog(DATABASE_DIR/'indexing/snapshots/index-v1.json'); "
        "assert c.digest()==s.digest(); print(len(c.postgresql),len(c.mongodb))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "DATABASE_SRC": str(packaged), "PYTHONPATH": os.pathsep.join(str(p) for p in sys.path)},
    )
    assert result.stdout.strip() == "98 19"


@pytest.mark.parametrize(
    "source",
    [
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version":true}',
        "[]",
        "{",
        '{"schema_version":1,"revision":"v1","postgresql":[],"mongodb":[],"typo":true}',
        '{"schema_version":1,"revision":"v1","postgresql":[],"mongodb":[],"x":NaN}',
        '{"schema_version":2,"revision":"v1","postgresql":[],"mongodb":[]}',
    ],
)
def test_bad_json_rejected_before_database_access(tmp_path, source):
    path = tmp_path / "catalog.json"
    path.write_text(source)
    with pytest.raises(ValueError):
        load_catalog(path)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p["mongodb"].append(deepcopy(p["mongodb"][0])),
        lambda p: p["postgresql"].append(deepcopy(p["postgresql"][0])),
        lambda p: p["mongodb"][0]["options"].update(uniqe=True),
        lambda p: p["mongodb"][0]["keys"][0].__setitem__(1, True),
        lambda p: p["mongodb"][0]["keys"][0].__setitem__(1, "1"),
        lambda p: p["mongodb"][0]["keys"].append(p["mongodb"][0]["keys"][0]),
        lambda p: p["mongodb"][0]["options"].update(sparse=True, partialFilterExpression={"deleted": False}),
        lambda p: p["mongodb"][1]["options"].update(expireAfterSeconds=10),
        lambda p: p["mongodb"][0]["options"].update(expireAfterSeconds=True),
        lambda p: p["mongodb"][0]["options"].update(expireAfterSeconds=-1),
        lambda p: p["mongodb"][0]["options"].update(partialFilterExpression={"$where": "return true"}),
        lambda p: p["postgresql"][0].update(table="product;DROP TABLE product"),
        lambda p: p["postgresql"][0].update(schema="private"),
        lambda p: p["postgresql"][0].update(method="hash"),
        lambda p: p["postgresql"][0]["keys"][0].update(order="descending"),
        lambda p: p["postgresql"][0].update(predicate={"column": "x", "op": "execute", "value": "sql"}),
        lambda p: p["postgresql"][0].update(predicate={"all": []}),
    ],
)
def test_invalid_definitions_are_rejected(payload, change):
    change(payload)
    with pytest.raises(ValidationError):
        IndexCatalog.model_validate(payload)


@pytest.mark.parametrize("field", ["attributes$**", "attributes..color", "attributes.", "$where", "a.$**.b"])
def test_invalid_mongo_key_paths(payload, field):
    payload["mongodb"][0]["keys"][0][0] = field
    with pytest.raises(ValidationError):
        IndexCatalog.model_validate(payload)


def test_compiler_keeps_key_order_partial_and_safe_literals():
    catalog = load_catalog()
    index = next(i for i in catalog.postgresql if i.name == "idx_product_visible_date_id")
    sql = create_sql(index)
    assert '"created_at" DESC NULLS FIRST, "product_id" ASC NULLS LAST' in sql
    assert 'WHERE (("status" = 1) AND ("is_deleted" = FALSE))' in sql
    assert literal("x'; DROP TABLE product; --\\") == "E'x''; DROP TABLE product; --\\\\'"
    with pytest.raises(ValueError):
        literal(float("inf"))
    with pytest.raises(ValueError):
        literal("nul\x00")
    with pytest.raises(ValueError, match="Constraint"):
        create_sql(next(i for i in catalog.postgresql if i.managed_by == "constraint"))


def test_gin_trigram_and_tsvector_are_compiled_from_manifest():
    statements = {i.name: create_sql(i) for i in load_catalog().postgresql if i.method == "gin"}
    assert '"gin_trgm_ops"' in statements["idx_product_title_trgm"]
    assert "to_tsvector(E'english', \"title\")" in statements["idx_product_title"]


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("status IN (E'pending',E'dead')", "(status = ANY (ARRAY['pending'::text, 'dead'::text]))"),
        ("((status = 1) AND (is_deleted = FALSE))", '(("status" = 1) AND ("is_deleted" = false))'),
        ("details ? E'aggregate'", "(details ? 'aggregate'::text)"),
        ("to_tsvector(E'english', \"title\")", "to_tsvector('english'::regconfig, title)"),
    ],
)
def test_catalog_expression_equivalence(left, right):
    assert expression_tree(left) == expression_tree(right)


def test_expression_comparison_preserves_strings_and_boolean_grouping():
    assert expression_tree("status='Success'") != expression_tree("status='success'")
    assert expression_tree("(a=1 OR b=2) AND c=3") != expression_tree("a=1 OR (b=2 AND c=3)")
    with pytest.raises(ValueError):
        expression_tree("lower(title) = 'test'")


def test_hash_ignores_object_property_order_but_preserves_compound_order(payload):
    original = IndexCatalog.model_validate(payload)
    assert IndexCatalog.model_validate(json.loads(json.dumps(payload, sort_keys=True))).digest() == original.digest()
    payload["mongodb"][1]["keys"].reverse()
    assert IndexCatalog.model_validate(payload).digest() != original.digest()


def test_text_signature_matches_server_representation():
    expected = signature([("description", "text"), ("tags", "text")], {})
    actual = signature(
        [("_fts", "text"), ("_ftsx", 1)],
        {
            "weights": {"tags": 1, "description": 1},
            "default_language": "english",
            "language_override": "language",
            "textIndexVersion": 3,
        },
    )
    assert actual == expected
    assert signature([("a", 1), ("b", -1)], {}) != signature([("b", -1), ("a", 1)], {})


class FakeCollection:
    def __init__(self, indexes):
        self.indexes = indexes
        self.created = []

    def index_information(self):
        return self.indexes

    def create_index(self, keys, **options):
        self.created.append(options["name"])
        self.indexes[options["name"]] = {"key": keys, **options}


class FakeDatabase:
    def __init__(self, indexes):
        self.collection = FakeCollection(indexes)

    def list_collection_names(self):
        return ["reviews"]

    def __getitem__(self, name):
        assert name == "reviews"
        return self.collection


def small_catalog():
    return IndexCatalog.model_validate(
        {
            "schema_version": 1,
            "revision": "test",
            "postgresql": [],
            "mongodb": [
                {
                    "collection": "reviews",
                    "keys": [["product_id", 1], ["created_at", -1]],
                    "options": {"name": "by_product"},
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "options",
    [
        {"unique": True},
        {"expireAfterSeconds": 10},
        {"partialFilterExpression": {"deleted": False}},
        {"hidden": True},
        {"collation": {"locale": "vi"}},
    ],
)
def test_mongo_conflict_prevents_all_creation(options):
    database = FakeDatabase({"by_product": {"key": [("product_id", 1), ("created_at", -1)], **options}})
    assert plan_mongo(database, small_catalog())["indexes"][0]["status"] == "conflict"
    with pytest.raises(ValueError, match="conflict"):
        apply_mongo(database, small_catalog(), record=False)
    assert database.collection.created == []


def test_mongo_document_paths_check_contracts_but_allow_dynamic_attributes():
    from app.schemas.documents import ProductDetails

    schema = ProductDetails.model_json_schema(by_alias=True)
    assert document_field(schema, "attributes.brand") is not None
    assert document_field(schema, "attributes.arbitrary.nested.key") is not None
    assert document_field(schema, "images.key") is not None
    assert document_field(schema, "attributes.$**") is not None
    assert document_field(schema, "unknown_field") is None
    assert document_field(schema, "images.wrong_key") is None


def test_mongo_unknown_field_or_nondatetime_ttl_is_a_conflict():
    payload = small_catalog().payload()
    payload["mongodb"][0]["keys"] = [["review_id", 1]]
    payload["mongodb"][0]["options"]["expireAfterSeconds"] = 10
    assert (
        "ttl_requires_date_contract:review_id"
        in plan_mongo(FakeDatabase({}), IndexCatalog.model_validate(payload))["indexes"][0]["reasons"]
    )
    payload["mongodb"][0]["keys"] = [["typo_field", 1]]
    payload["mongodb"][0]["options"].pop("expireAfterSeconds")
    assert (
        "unknown_document_field:typo_field"
        in plan_mongo(FakeDatabase({}), IndexCatalog.model_validate(payload))["indexes"][0]["reasons"]
    )


def test_mongo_additive_apply_is_idempotent_and_keeps_unmanaged():
    database = FakeDatabase({"_id_": {"key": [("_id", 1)]}, "external": {"key": [("other", 1)]}})
    first = apply_mongo(database, small_catalog(), record=False)
    second = apply_mongo(database, small_catalog(), record=False)
    assert len(first["created"]) == 1 and second["created"] == []
    assert set(database.collection.indexes) == {"_id_", "external", "by_product"}


def test_mongo_equivalent_index_with_different_name_is_reported():
    database = FakeDatabase({"old_name": {"key": [("product_id", 1), ("created_at", -1)]}})
    assert plan_mongo(database, small_catalog())["indexes"][0]["status"] == "conflict"


def test_apply_stops_when_an_engine_preflight_cannot_complete(monkeypatch):
    from scripts import indexes

    calls = []

    def unavailable_plan(command, engine, catalog_path):
        calls.append((command, engine))
        return {"result": "FAIL", "engines": {}, "failed_engine": engine, "error": "unavailable"}

    monkeypatch.setattr(indexes, "execute", unavailable_plan)
    result = execute("apply", "all")
    assert result["result"] == "FAIL" and result["engines"] == {}
    assert calls == [("plan", "postgresql")]


def test_removal_or_replacement_requires_explicit_versioned_work(payload):
    previous = IndexCatalog.model_validate(payload)
    payload["postgresql"].pop()
    with pytest.raises(ValueError, match="explicit reviewed SQL"):
        require_additive(previous, IndexCatalog.model_validate(payload))


def test_snapshot_tampering_is_rejected(tmp_path):
    catalog = load_catalog()
    snapshots = tmp_path / "indexing/snapshots"
    snapshots.mkdir(parents=True)
    snapshot = snapshots / (catalog.revision + ".json")
    snapshot.write_text(json.dumps(catalog.payload()))
    migration = tmp_path / "008_test.sql"
    migration.write_text(f"-- index-catalog: {catalog.revision} {catalog.digest()}\nSELECT 1;")
    (tmp_path / "indexing/releases.json").write_text(
        json.dumps([{"migration": "008", "revision": catalog.revision, "sha256": catalog.digest()}])
    )
    validate_migration_snapshot(migration, tmp_path)
    payload = catalog.payload()
    payload["mongodb"][0]["options"]["unique"] = False
    snapshot.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum"):
        validate_migration_snapshot(migration, tmp_path)
    migration.write_text("SELECT 1;")
    with pytest.raises(ValueError, match="binding"):
        validate_migration_snapshot(migration, tmp_path)
