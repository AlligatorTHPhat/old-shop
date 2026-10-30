"""Partial upserts, not replace_one: preserve all Mongo-owned attributes/moderation/files."""

from datetime import UTC, datetime

from app.services.mongo import get_database
from etl.extract import SOURCES
from etl.pipelines.documents import OWNED
from etl.transform import document_id


def pg_fields(collection, document):
    return {key: value for key, value in document.items() if key not in OWNED.get(collection, set()) and key != "_id"}


def selector(entity, key, document=None):
    column = SOURCES[entity][1]
    result = {column: key["id"]}
    if entity == "system_log":
        if document is not None:
            result["created_at"] = document["created_at"]
        else:
            result["etl.source_created_at"] = document_id(entity, key).split(":", 2)[2]
    return result


def apply(entity, key, document, database=None, run_id=None):
    database = database if database is not None else get_database()
    name = SOURCES[entity][2]
    collection = database[name]
    identifier = document_id(entity, key)
    query = selector(entity, key, document)
    if document is None:
        # Retained metadata survives hard deletes; absence is already a valid deleted projection.
        if entity == "system_log":
            collection.delete_one(query)
        else:
            collection.update_one(
                query, {"$set": {"deleted": True, "etl": {"synced_at": datetime.now(UTC), "run_id": str(run_id)}}}
            )
        return
    if entity == "product":
        from etl.pipelines.media import ensure_images

        ensure_images(document)
    defaults = {key: document[key] for key in OWNED.get(name, set())}
    defaults["_id"] = identifier
    if name == "reviews":
        defaults["status"] = "pending"
    collection.update_one(query, {"$set": pg_fields(name, document), "$setOnInsert": defaults}, upsert=True)
