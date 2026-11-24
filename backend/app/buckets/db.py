"""Bounded independent database transactions; never pretend a core/site commit is atomic."""

import json
from contextlib import contextmanager
from functools import lru_cache

import psycopg2
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor
from psycopg2.pool import PoolError, ThreadedConnectionPool

from app.core.config import settings
from app.services.allocation import AllocationError, Allocator, site_identifier, validate_target

_pools = []


def site_urls() -> dict[str, str]:
    values = json.loads(settings.BUCKET_SITE_URLS)
    if not isinstance(values, dict) or not values:
        raise AllocationError("BUCKET_SITE_URLS must map site identifiers to configured DSNs")
    for key, value in values.items():
        site_identifier(key)
        if not isinstance(value, str) or not value.startswith(("postgresql://", "postgres://")):
            raise AllocationError("Invalid site DSN")
    return values


@lru_cache(maxsize=16)
def pool(site: str | None = None):
    options = {"connect_timeout": 4, "application_name": "oldshop-bucket-v2"}
    if site is None:
        result = ThreadedConnectionPool(1, 6, **settings.database_connect_args, **options)
        _pools.append(result)
        return result
    dsn = site_urls().get(site)
    if not dsn:
        raise AllocationError("Registered site has no configured DSN")
    result = ThreadedConnectionPool(1, 4, dsn, **options)
    _pools.append(result)
    return result


@contextmanager
def transaction(site: str | None = None, route=None, maintenance=False):
    connection = None
    try:
        connection = pool(site).getconn()
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            cursor.execute("SET LOCAL statement_timeout='15s'")
            cursor.execute("SET LOCAL lock_timeout='5s'")
            if maintenance:
                cursor.execute("SET LOCAL oldshop.maintenance='on'")
            if route is not None:
                cursor.execute("SELECT set_config('oldshop.ownership_epoch',%s,true)", (str(route.ownership_epoch),))
                cursor.execute(
                    "SELECT i.site_id,i.contract_digest,l.ownership_epoch,l.state FROM bucket_installation i "
                    "JOIN bucket_lease l ON l.bucket_id=%s FOR SHARE OF l",
                    (route.bucket_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise AllocationError("Missing bucket lease")
                validate_target(
                    route, dict(zip(("site_id", "contract_digest", "ownership_epoch", "state"), row, strict=True))
                )
        yield connection
        connection.commit()
    except (psycopg2.Error, PoolError, AllocationError) as error:
        if connection:
            connection.rollback()
        if isinstance(error, psycopg2.IntegrityError):
            raise HTTPException(409, "Dữ liệu xung đột với ràng buộc nghiệp vụ.") from error
        raise HTTPException(503, "Kho dữ liệu hoặc định tuyến đang tạm thời không khả dụng.") from error
    except BaseException:
        if connection:
            connection.rollback()
        raise
    finally:
        if connection:
            pool(site).putconn(connection)


def rows(connection, query: str, params=()) -> list[dict]:
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def one(connection, query: str, params=()) -> dict | None:
    result = rows(connection, query, params)
    return result[0] if result else None


def execute(connection, query: str, params=()):
    with connection.cursor() as cursor:
        cursor.execute(query, params)


def product_route(product_id: int):
    try:
        with transaction() as core:
            return Allocator(core).resolve_product(product_id)
    except KeyError as error:
        raise HTTPException(404, "Product not found") from error


def shutdown():
    for existing in _pools:
        existing.closeall()
    _pools.clear()
    pool.cache_clear()
