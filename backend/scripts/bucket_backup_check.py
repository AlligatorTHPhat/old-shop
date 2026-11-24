"""Rehearse SQL/Mongo restore into NEW databases. Run during a maintenance window."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import psycopg2
from bson import decode_all, encode
from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.buckets.db import rows, site_urls, transaction
from app.core.config import settings
from app.services.mongo import get_database


def digest_sql(connection):
    tables = rows(
        connection,
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('r','p') AND NOT c.relispartition ORDER BY c.relname",
    )
    result = {}
    for table in tables:
        data = rows(connection, sql.SQL("SELECT * FROM {}").format(sql.Identifier(table["relname"])))
        canonical = sorted(json.dumps(row, sort_keys=True, default=str) for row in data)
        result[table["relname"]] = dict(
            count=len(data), sha256=hashlib.sha256("\n".join(canonical).encode()).hexdigest()
        )
    return result


def check(output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    with transaction() as core:
        sites = [
            row["site_id"] for row in rows(core, "SELECT site_id FROM site_registry WHERE active ORDER BY site_id")
        ]
    suffix = uuid.uuid4().hex[:8]
    report = dict(sql={}, mongo={}, media={})
    for label in [None, *sites]:
        url = make_url(settings.DATABASE_URL if label is None else site_urls()[label])
        target = f"bucket_restore_{suffix}_{(label or 'core').lower()}"
        env = {
            **os.environ,
            "PGHOST": url.host,
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username,
            "PGPASSWORD": url.password,
            "PGDATABASE": url.database,
        }
        archive = output / f"{label or 'core'}.dump"
        with transaction(label) as original:
            before = digest_sql(original)
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(archive)],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        admin = psycopg2.connect(
            host=url.host, port=url.port, user=url.username, password=url.password, dbname=url.database
        )
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        admin.close()
        restore_sql = output / f"{label or 'core'}-restore.sql"
        subprocess.run(
            ["pg_restore", "--no-owner", "--no-privileges", "--file", str(restore_sql), str(archive)],
            env={**env, "PGDATABASE": target},
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # Debian's PG17 client writes this header even for a PG16 source. It is
        # a session option introduced in PG17; remove only that exact header.
        if original.server_version < 170000:
            restore_sql.write_text(restore_sql.read_text().replace("SET transaction_timeout = 0;\n", ""))
        subprocess.run(
            ["psql", "-X", "--set", "ON_ERROR_STOP=1", "--file", str(restore_sql)],
            env={**env, "PGDATABASE": target},
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        restored = psycopg2.connect(
            host=url.host, port=url.port, user=url.username, password=url.password, dbname=target
        )
        with restored:
            after = digest_sql(restored)
        restored.close()
        if before != after:
            raise ValueError(f"Restore digest mismatch for {label or 'core'}; stop writes before retrying")
        report["sql"][label or "core"] = dict(
            database=target, tables=before, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
        )
    database = get_database()
    target = database.client[f"bucket_restore_{suffix}"]
    for name in sorted(database.list_collection_names()):
        collection = database[name]
        documents = list(collection.find().sort("_id", 1))
        archive = output / f"mongo-{name}.bson"
        archive.write_bytes(b"".join(encode(document) for document in documents))
        options = {
            key: value
            for key, value in collection.options().items()
            if key in {"validator", "validationLevel", "validationAction", "collation"}
        }
        clone = target.create_collection(name, **options)
        if documents:
            clone.insert_many(decode_all(archive.read_bytes()))
        for index in collection.list_indexes():
            if index["name"] != "_id_":
                keys = list(index["key"].items())
                if "_fts" in index["key"]:
                    keys = [(key, "text") for key in index["weights"]] + [
                        (key, value) for key, value in keys if key not in {"_fts", "_ftsx"}
                    ]
                clone.create_index(
                    keys,
                    **{
                        key: value
                        for key, value in index.items()
                        if key
                        in {
                            "name",
                            "unique",
                            "sparse",
                            "expireAfterSeconds",
                            "partialFilterExpression",
                            "weights",
                            "default_language",
                            "language_override",
                        }
                    },
                )
        restored = b"".join(encode(document) for document in clone.find().sort("_id", 1))
        if restored != archive.read_bytes():
            raise ValueError("Mongo restore mismatch")
        report["mongo"][name] = dict(count=len(documents), sha256=hashlib.sha256(restored).hexdigest())
    report["mongo_database"] = target.name
    # Back up binary media too; checksum inventory alone is not a backup.
    for path in sorted(settings.MEDIA_DIR.rglob("*")):
        if path.is_file():
            relative = path.relative_to(settings.MEDIA_DIR)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            copied = output / "media" / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, copied)
            if hashlib.sha256(copied.read_bytes()).hexdigest() != digest:
                raise ValueError("Media changed while backing up; stop writes and retry")
            report["media"][str(relative)] = digest
    report["ok"] = True
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    return dict(
        ok=True,
        sql_databases={key: value["database"] for key, value in report["sql"].items()},
        mongo_database=target.name,
        media_files=len(report["media"]),
        report=str(output / "report.json"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    try:
        print(json.dumps(check(parser.parse_args().output)))
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode(errors="replace")[:2000]
        raise SystemExit(
            f"Backup/restore command failed (exit {error.returncode}); no source data deleted\n{detail}"
        ) from None
