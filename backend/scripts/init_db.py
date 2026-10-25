"""Bootstrap the database and media volume. Safe to run on every container start.

1. wait until PostgreSQL accepts connections
2. create the database if it does not exist
3. if the schema is missing, run database/init.sql (schema, functions, seed data) with psql
4. copy seed images into MEDIA_DIR without overwriting user uploads

Usage: python -m scripts.init_db   (from backend/, or the container WORKDIR)
"""

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402

logger = logging.getLogger("init_db")

DATABASE_DIR = Path(os.getenv("DATABASE_SRC", Path(__file__).resolve().parents[2] / "database"))
SEED_MEDIA_DIR = DATABASE_DIR / "03_seeds" / "media"


def connect(dbname: str):
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        dbname=dbname,
    )


def wait_for_server(retries: int = 30, delay: float = 2.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            connect("postgres").close()
            return
        except psycopg2.OperationalError:
            logger.info("Waiting for PostgreSQL (%s/%s)...", attempt, retries)
            time.sleep(delay)
    raise SystemExit("PostgreSQL is not reachable")


def ensure_database() -> None:
    conn = connect("postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.DB_NAME,))
        if not cur.fetchone():
            logger.info("Creating database %s", settings.DB_NAME)
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.DB_NAME)))
    conn.close()


def schema_exists() -> bool:
    with connect(settings.DB_NAME) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.\"user\"') IS NOT NULL")
        return cur.fetchone()[0]


def load_schema() -> None:
    logger.info("Loading schema and seed data from %s", DATABASE_DIR / "init.sql")
    subprocess.run(
        [
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
            "-h",
            settings.DB_HOST,
            "-p",
            str(settings.DB_PORT),
            "-U",
            settings.DB_USER,
            "-d",
            settings.DB_NAME,
            "-f",
            "init.sql",
        ],
        cwd=DATABASE_DIR,  # init.sql uses \i with paths relative to this folder
        env={**os.environ, "PGPASSWORD": settings.DB_PASSWORD},
        check=True,
    )


def sync_seed_media() -> None:
    if not SEED_MEDIA_DIR.is_dir():
        return
    copied = 0
    for src in SEED_MEDIA_DIR.rglob("*"):
        dest = settings.MEDIA_DIR / src.relative_to(SEED_MEDIA_DIR)
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif not dest.exists():
            shutil.copy2(src, dest)
            copied += 1
    if copied:
        logger.info("Copied %s seed media files into %s", copied, settings.MEDIA_DIR)


def main() -> None:
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    wait_for_server()
    ensure_database()
    if schema_exists():
        logger.info("Schema already present, skipping init.sql")
    else:
        load_schema()
    sync_seed_media()


if __name__ == "__main__":
    main()
