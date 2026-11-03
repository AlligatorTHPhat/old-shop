"""Idempotently create/update Day 3 validators and indexes; never seed or drop data."""

import json

from app.services.index_config import load_catalog
from app.services.index_mongo import apply_mongo, plan_mongo
from app.services.mongo import get_database
from app.services.mongo_schema import validators


def initialize(database=None, catalog=None) -> dict:
    database = database if database is not None else get_database()
    catalog = catalog or load_catalog()
    plan = plan_mongo(database, catalog)
    if any(i["status"] == "conflict" for i in plan["indexes"]):
        raise ValueError("Mongo index conflict; run scripts.plan_indexes --engine mongodb")
    existing = set(database.list_collection_names())
    for name, validator in validators().items():
        options = {"validator": validator, "validationLevel": "strict", "validationAction": "error"}
        if name in existing:
            database.command("collMod", name, **options)
        else:
            database.create_collection(name, **options)
    from etl.errors import initialize as initialize_errors

    initialize_errors(database, catalog=catalog)
    result = apply_mongo(database, catalog)
    return {
        "collections": sorted({i.collection for i in catalog.mongodb}),
        "validation": "strict/error",
        "revision": catalog.revision,
        "indexes": result,
    }


if __name__ == "__main__":
    print(json.dumps(initialize()))
