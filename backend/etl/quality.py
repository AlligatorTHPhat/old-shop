"""Counts every cycle; full source-key/PG-field comparisons daily and on full/reconcile."""

from datetime import UTC, datetime, timedelta

from psycopg2 import sql

from app.core.config import settings
from app.services.storage import bucket_for, minio_client, validate_path
from etl.extract import SOURCES
from etl.load import pg_fields, selector
from etl.pipelines.documents import project
from etl.transform import comparable


def check(source, database, run_id, deep=False, touched=()):
    result = {"collections": {}, "media": {"referenced": 0, "found": 0, "errors": 0}, "mismatches": 0}
    cutoff = datetime.now(UTC) - timedelta(days=90)
    for entity, (table, _, collection) in SOURCES.items():
        predicate = " WHERE NOT is_deleted" if entity in ("product", "order", "review") else ""
        query = sql.SQL("SELECT count(*) AS n FROM {}" + predicate).format(sql.Identifier(table))
        if entity == "system_log":
            query = sql.SQL("""SELECT count(*) AS n FROM system_log s JOIN etl_time_origin t
                ON t.source_table='system_log'
                AND t.source_key=jsonb_build_object('log_id',s.log_id,'created_at',s.created_at)
                AND t.field_name='created_at' AND t.source_value=s.created_at
                WHERE s.created_at AT TIME ZONE t.source_zone >= %s""")
            expected = source.rows(query, (cutoff,))[0]["n"]
        else:
            expected = source.rows(query)[0]["n"]
        match = {"deleted": {"$ne": True}}
        if entity == "system_log":
            match["created_at"] = {"$gte": cutoff}
        actual = database[collection].count_documents(match)
        item = {"pg_active": expected, "mongo_active": actual, "field_mismatches": 0, "projection_errors": 0}
        keys = source.keys(entity) if deep else [key for kind, key in touched if kind == entity]
        for key in keys:
            try:
                document = project(source, entity, key, run_id)
                stored = database[collection].find_one(selector(entity, key, document))
                if document is None:
                    if stored and not stored.get("deleted", False):
                        item["field_mismatches"] += 1
                elif stored is None:
                    item["field_mismatches"] += 1
                else:
                    fields = pg_fields(collection, document)
                    fields.pop("etl", None)
                    if comparable(fields) != comparable({name: stored.get(name) for name in fields}):
                        item["field_mismatches"] += 1
            except Exception:
                item["projection_errors"] += 1
        result["collections"][collection] = item
        result["mismatches"] += abs(expected - actual) + item["field_mismatches"] + item["projection_errors"]
    if deep and settings.MINIO_ACCESS_KEY and settings.MINIO_SECRET_KEY:
        images = source.rows("SELECT image_url,content_type,size_bytes FROM product_image")
        for image in images:
            result["media"]["referenced"] += 1
            try:
                path = validate_path(image["image_url"].removeprefix("/media/"))
                stat = minio_client().stat_object(bucket_for(path), path)
                if stat.size != image["size_bytes"] or stat.content_type != image["content_type"]:
                    result["media"]["errors"] += 1
                else:
                    result["media"]["found"] += 1
            except Exception:
                result["media"]["errors"] += 1
        result["mismatches"] += result["media"]["errors"]
    return result
