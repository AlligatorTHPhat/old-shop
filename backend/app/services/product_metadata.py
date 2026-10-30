"""Mongo owns attributes/tags only; current prices, stock and visibility always come from PG."""

import json
import math
import re
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field, JsonValue, ValidationError
from pymongo.errors import PyMongoError

from app.core.config import settings
from app.services.mongo import get_database

KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
MAX_MATCHES = 5000


class PublicMetadata(BaseModel):
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


def read(product_id: int, category_id: int) -> dict:
    fallback = {"attributes": {}, "tags": [], "metadata_status": "unavailable", "metadata_synced_at": None}
    if not settings.MONGO_URI:
        return fallback
    try:
        row = get_database().product_details.find_one(
            {"product_id": product_id, "category_id": category_id, "deleted": False},
            {"attributes": 1, "tags": 1, "etl.synced_at": 1},
            max_time_ms=2000,
        )
        if row is None:
            return {**fallback, "metadata_status": "missing"}
        metadata = PublicMetadata.model_validate(row)
        synced = (row.get("etl") or {}).get("synced_at")
        return {
            **metadata.model_dump(),
            "metadata_status": "available",
            "metadata_synced_at": synced if isinstance(synced, datetime) else None,
        }
    except (PyMongoError, ValidationError):
        return fallback


def parse_filters(raw: str) -> dict:
    try:
        values = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "attributes must be a JSON object of scalar equality filters") from exc
    if not isinstance(values, dict) or not 1 <= len(values) <= 16:
        raise HTTPException(422, "attributes must contain 1 to 16 filters")
    for key, value in values.items():
        if not KEY.fullmatch(key) or not isinstance(value, (str, bool, int, float)):
            raise HTTPException(422, "Attribute keys must be simple names and values must be scalars")
        if isinstance(value, float) and not math.isfinite(value):
            raise HTTPException(422, "Attribute numbers must be finite")
        if isinstance(value, int) and not -(2**63) <= value < 2**63:
            raise HTTPException(422, "Attribute integer exceeds BSON int64")
    return values


def matching_ids(filters: dict) -> list[int]:
    if not settings.MONGO_URI:
        raise HTTPException(503, "Attribute search unavailable")
    query = {"deleted": False, **{f"attributes.{key}": value for key, value in filters.items()}}
    try:
        with (
            get_database()
            .product_details.find(query, {"product_id": 1, "_id": 0})
            .max_time_ms(2000)
            .limit(MAX_MATCHES + 1) as cursor
        ):
            rows = list(cursor)
    except PyMongoError as exc:
        raise HTTPException(503, "Attribute search unavailable") from exc
    if len(rows) > MAX_MATCHES:
        raise HTTPException(422, "Too many attribute matches; narrow the filters")
    return [
        int(row["product_id"])
        for row in rows
        if isinstance(row.get("product_id"), int)
        and not isinstance(row["product_id"], bool)
        and 0 < row["product_id"] < 2**63
    ]
