"""Sanitized durable dead-letter records; PG outbox remains authoritative if Mongo is down."""

from contextlib import suppress
from datetime import UTC, datetime

from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.schemas.etl import ErrorKey as ErrorKey
from app.schemas.etl import ETLError
from app.services.index_config import IndexCatalog, load_catalog
from app.services.index_mongo import apply_mongo
from app.services.mongo_schema import bson_schema
from etl.transform import QualityError


def initialize(database, catalog=None):
    catalog = catalog or load_catalog()
    subset = IndexCatalog(
        schema_version=1,
        revision=catalog.revision,
        postgresql=[],
        mongodb=[i for i in catalog.mongodb if i.collection == "etl_errors"],
    )
    options = {
        "validator": {"$jsonSchema": bson_schema(ETLError)},
        "validationLevel": "strict",
        "validationAction": "error",
    }
    if "etl_errors" in database.list_collection_names():
        database.command("collMod", "etl_errors", **options)
    else:
        database.create_collection("etl_errors", **options)
    apply_mongo(database, subset, record=False)


def code(error):
    if isinstance(error, RuntimeError) and str(error) == "etl_worker_busy":
        return "etl_worker_busy"
    if isinstance(error, QualityError):
        return error.code
    if isinstance(error, ValidationError):
        return "document_validation_failed"
    if isinstance(error, PyMongoError):
        return "mongo_unavailable_or_write_rejected"
    return "dependency_or_database_error"


def record(database, event, run_id, error_code, attempts):
    data = ETLError(
        _id=f"event:{event['event_id']}",
        event_id=event["event_id"],
        run_id=str(run_id),
        entity_type=event["entity_type"],
        entity_key=event["entity_key"],
        code=error_code,
        attempts=attempts,
        last_at=datetime.now(UTC),
    ).model_dump(by_alias=True)
    # PG already retains failures; Mongo downtime must never turn failure into ACK.
    with suppress(PyMongoError):
        database.etl_errors.update_one({"_id": data["_id"]}, {"$set": data}, upsert=True)


def resolve(database, event_id):
    database.etl_errors.update_one({"_id": f"event:{event_id}"}, {"$set": {"resolved": True}})
