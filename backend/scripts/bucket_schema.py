"""Explicit schema-only bootstrap for a NEW bucket database. Refuses legacy databases."""

import argparse
import hashlib
import os
from pathlib import Path

import psycopg2

from app.core.config import settings
from app.services.allocation import load_contract

DATABASE = Path(os.getenv("DATABASE_SRC", Path(__file__).resolve().parents[2] / "database"))


def source(kind: str) -> str:
    paths = []
    for line in (DATABASE / "init.sql").read_text().splitlines():
        if line.startswith("\\i ") and not line[3:].startswith("03_seeds/"):
            paths.append(DATABASE / line[3:].strip())
    paths.extend(sorted((DATABASE / "04_migrations").glob("[0-9][0-9][0-9]_*.sql")))
    paths.append(DATABASE / "distributed/bucket/001_common.sql")
    paths.append(DATABASE / f"distributed/bucket/{'002_core' if kind == 'core' else '003_site'}.sql")
    return "\n".join(path.read_text() for path in paths)


def initialize(connection, kind: str, dataset_id: str, site_id: str | None = None):
    body = source(kind)
    digest = hashlib.sha256(body.encode()).hexdigest()
    with connection, connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(7363196017)")
        cursor.execute("SELECT to_regclass('bucket_installation')")
        if cursor.fetchone()[0]:
            cursor.execute("SELECT kind,site_id,dataset_id,contract_digest,schema_digest FROM bucket_installation")
            if cursor.fetchone() != (kind, site_id, dataset_id, load_contract().digest(), digest):
                raise ValueError("Installation/schema differs: explicit migration required")
            return
        cursor.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
        if cursor.fetchone()[0]:
            raise ValueError("Refusing schema bootstrap on a nonempty legacy database; use migration to a new target")
        cursor.execute(body)
        cursor.execute(
            "INSERT INTO bucket_installation(kind,site_id,dataset_id,contract_digest,schema_digest) "
            "VALUES(%s,%s,%s,%s,%s)",
            (kind, site_id, dataset_id, load_contract().digest(), digest),
        )


def main():
    from app.buckets.db import site_urls

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["core", "site"], required=True)
    parser.add_argument("--site")
    args = parser.parse_args()
    if args.kind == "site" and args.site not in site_urls():
        parser.error("A configured --site is required")
    connection = (
        psycopg2.connect(site_urls()[args.site])
        if args.kind == "site"
        else psycopg2.connect(**settings.database_connect_args)
    )
    try:
        initialize(connection, args.kind, settings.BUCKET_DATASET, args.site)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
