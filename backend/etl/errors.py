"""Sanitized durable dead-letter records; PG outbox remains authoritative if Mongo is down."""

from contextlib import suppress
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, Field, ValidationError
from pymongo.errors import PyMongoError

from app.schemas.documents import DocumentModel, Identifier
from app.services.mongo_schema import bson_schema
from etl.transform import QualityError


class ErrorKey(DocumentModel):
    id: Identifier
    created_at: str | None = None


class ETLError(DocumentModel):
    id: str = Field(alias="_id")
    event_id: int
    run_id: str
    entity_type: Literal["product", "order", "review", "system_log", "violation_log", "contact"]
    entity_key: ErrorKey
    code: str = Field(max_length=80)
    attempts: int = Field(ge=1)
    last_at: AwareDatetime
    resolved: bool = False


def initialize(database):
    options = {
        "validator": {"$jsonSchema": bson_schema(ETLError)},
        "validationLevel": "strict",
        "validationAction": "error",
    }
    if "etl_errors" in database.list_collection_names():
        database.command("collMod", "etl_errors", **options)
    else:
        database.create_collection("etl_errors", **options)
    database.etl_errors.create_index([("resolved", 1), ("last_at", 1)])


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
