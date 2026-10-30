"""Idempotently create/update Day 3 validators and indexes; never seed or drop data."""

import json

from app.services.mongo import get_database
from app.services.mongo_schema import INDEXES, validators


def initialize(database=None) -> dict:
    database = database if database is not None else get_database()
    existing = set(database.list_collection_names())
    for name, validator in validators().items():
        options = {"validator": validator, "validationLevel": "strict", "validationAction": "error"}
        if name in existing:
            database.command("collMod", name, **options)
        else:
            database.create_collection(name, **options)
        for keys, options in INDEXES[name]:
            database[name].create_index(keys, **options)
    from etl.errors import initialize as initialize_errors

    initialize_errors(database)
    return {"collections": sorted(INDEXES), "validation": "strict/error"}


if __name__ == "__main__":
    print(json.dumps(initialize()))
