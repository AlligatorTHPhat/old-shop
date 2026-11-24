"""Initialize new isolated core/sites and an explicit initial bucket mapping; no demo data."""

import argparse
import hashlib

import psycopg2

from app.buckets.db import execute, one, rows, site_urls, transaction
from app.core.config import settings
from scripts.bucket_schema import DATABASE, initialize


def extensions(connection, kind):
    with connection, connection.cursor() as cursor:
        cursor.execute("CREATE TABLE IF NOT EXISTS bucket_extension(name text PRIMARY KEY,checksum text NOT NULL)")
        for name in (
            [
                "005_payments.sql",
                "006_fulfillment.sql",
                "007_import.sql",
                "008_graph_generation.sql",
                "009_seed_manifest.sql",
            ]
            if kind == "core"
            else ["004_runtime.sql"]
        ):
            content = (DATABASE / "distributed/bucket" / name).read_text()
            digest = hashlib.sha256(content.encode()).hexdigest()
            cursor.execute("SELECT checksum FROM bucket_extension WHERE name=%s", (name,))
            found = cursor.fetchone()
            if found:
                if found[0] != digest:
                    raise ValueError("Bucket extension checksum changed; add a migration instead")
            else:
                cursor.execute(content)
                cursor.execute("INSERT INTO bucket_extension VALUES(%s,%s)", (name, digest))


def setup(sites=("A", "B")):
    connection = psycopg2.connect(**settings.database_connect_args)
    try:
        initialize(connection, "core", settings.BUCKET_DATASET)
        extensions(connection, "core")
    finally:
        connection.close()
    for site_id in sites:
        connection = psycopg2.connect(site_urls()[site_id])
        try:
            initialize(connection, "site", settings.BUCKET_DATASET, site_id)
            extensions(connection, "site")
        finally:
            connection.close()
    with transaction() as core:
        for site_id in sites:
            execute(
                core,
                "INSERT INTO site_registry(site_id,dsn_alias) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (site_id, site_id),
            )
        if not one(core, "SELECT bucket_id FROM bucket_assignment LIMIT 1"):
            if not {"A", "B"}.issubset(sites):
                raise ValueError("Initial setup requires A and B")
            execute(
                core,
                "INSERT INTO bucket_assignment(bucket_id,owner_site_id) SELECT value,"
                "CASE WHEN value<128 THEN 'A' ELSE 'B' END FROM generate_series(0,255) value",
            )
        mapping = rows(core, "SELECT * FROM bucket_assignment")
    for site_id in sites:
        with transaction(site_id) as site:
            for assignment in mapping:
                if assignment["owner_site_id"] == site_id:
                    execute(
                        site,
                        "INSERT INTO bucket_lease VALUES(%s,%s,'active') ON CONFLICT DO NOTHING",
                        (assignment["bucket_id"], assignment["ownership_epoch"]),
                    )
    if settings.MONGO_URI:
        from app.services.mongo import get_database

        database = get_database()
        with transaction() as core:
            instance = str(one(core, "SELECT instance_id FROM bucket_installation")["instance_id"])
            seeded = bool(one(core, "SELECT run_id FROM seed_runs LIMIT 1"))
        marker = database.bucket_installation.find_one({"_id": "bucket-v2"})
        if marker is None and database.product_details.count_documents({}) and not seeded:
            raise ValueError("Mongo target is nonempty and unbound; use a new projection database")
        database.bucket_installation.update_one(
            {"_id": "bucket-v2"},
            {"$setOnInsert": {"core_instance": instance, "dataset_id": settings.BUCKET_DATASET}},
            upsert=True,
        )
        marker = database.bucket_installation.find_one({"_id": "bucket-v2"})
        if marker["core_instance"] != instance or marker["dataset_id"] != settings.BUCKET_DATASET:
            raise ValueError("Mongo database belongs to a different installation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", nargs="+", default=["A", "B"])
    setup(tuple(parser.parse_args().sites))
    print("Bucket schema/identity verified; no business seed applied.")
