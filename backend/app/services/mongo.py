"""Bounded-time synchronous client; call from sync handlers or a thread pool."""

from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError
from pymongo.write_concern import WriteConcern

from app.core.config import settings


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    if not settings.MONGO_URI:
        raise ValueError("MONGO_URI is not configured")
    return MongoClient(
        settings.MONGO_URI,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
        tz_aware=True,
        appname="oldshop",
    )


def get_database() -> Database:
    return get_client().get_database(settings.MONGO_DB, write_concern=WriteConcern(w="majority", wtimeout=5000))


def get_collection(name: str) -> Collection:
    from app.schemas.documents import DOCUMENT_MODELS

    if name not in DOCUMENT_MODELS:
        raise ValueError("Unknown application collection")
    return get_database().get_collection(name)


def ping_mongo() -> bool:
    try:
        get_database().command("ping")
        return True
    except (PyMongoError, ValueError):
        return False
