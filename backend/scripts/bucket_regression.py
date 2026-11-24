"""Run the legacy suite in a new database inside the isolated bucket core cluster."""

import os
import subprocess
import sys
import uuid

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.core.config import settings


def main():
    name = "bucket_regression_" + uuid.uuid4().hex[:8]
    connection = psycopg2.connect(**settings.database_connect_args)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    env = {
        **os.environ,
        "DATABASE_URL": make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False),
        "BUCKET_MODE": "false",
        "GRAPH_ENABLED": "false",
        "MONGO_URI": "",
        "MONGO_DB": name,
        "MEDIA_DIR": "/tmp/" + name + "_media",
        "ENVIRONMENT": "test",
        "STORAGE_BACKEND": "local",
    }
    subprocess.run([sys.executable, "-m", "scripts.init_db"], env=env, check=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-o", "cache_dir=/tmp/legacy-test-cache", "tests", "-q"],
        env=env,
    )
    connection.close()
    print(f"Legacy regression database retained: {name}")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
