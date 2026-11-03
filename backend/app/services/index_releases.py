"""Immutable snapshot bindings to existing transactional migration history."""

import hashlib
import json
import re
from pathlib import Path

from app.services.index_config import DATABASE_DIR, load_catalog, no_duplicates

HEADER = re.compile(r"^-- index-catalog: ([A-Za-z0-9_-]+) ([0-9a-f]{64})$", re.MULTILINE)


def validate_migration_snapshot(path, database_dir=DATABASE_DIR):
    headers = HEADER.findall(Path(path).read_text())
    bindings_path = Path(database_dir) / "indexing/releases.json"
    bindings = json.loads(bindings_path.read_text(), object_pairs_hook=no_duplicates) if bindings_path.exists() else []
    expected = [
        (r["revision"], r["sha256"])
        for r in bindings
        if r["migration"] == Path(path).name[:3] and "baseline_migrations" not in r
    ]
    if (headers or expected) and headers != expected:
        raise ValueError("Index migration snapshot header/release binding mismatch")
    if not headers:
        return
    if len(headers) != 1:
        raise ValueError("Duplicate index snapshot header")
    revision, digest = headers[0]
    snapshot = load_catalog(Path(database_dir) / "indexing/snapshots" / (revision + ".json"))
    if snapshot.revision != revision or snapshot.digest() != digest:
        raise ValueError("Index migration snapshot checksum mismatch")


def release_catalog(connection, database_dir=DATABASE_DIR):
    database_dir = Path(database_dir)
    releases = json.loads((database_dir / "indexing/releases.json").read_text(), object_pairs_hook=no_duplicates)
    with connection.cursor() as cursor:
        cursor.execute("SELECT version,checksum FROM public.schema_migrations ORDER BY version")
        history = dict(cursor.fetchall())
    files = sorted((database_dir / "04_migrations").glob("[0-9][0-9][0-9]_*.sql"))
    versions = [p.name[:3] for p in files]
    if list(history) != versions[: len(history)]:
        raise ValueError("Unrecognized migration history")
    for path in files:
        if path.name[:3] in history:
            if hashlib.sha256(path.read_bytes()).hexdigest() != history[path.name[:3]]:
                raise ValueError("Applied migration checksum mismatch")
            validate_migration_snapshot(path, database_dir)
    selected = None
    seen = set()
    for release in sorted(releases, key=lambda r: r["migration"]):
        if release["migration"] in seen:
            raise ValueError("Duplicate index release migration")
        seen.add(release["migration"])
        revision = release["revision"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", revision):
            raise ValueError("Invalid snapshot revision")
        if release["migration"] not in history:
            continue
        catalog = load_catalog(database_dir / "indexing/snapshots" / (revision + ".json"))
        if catalog.digest() != release["sha256"] or catalog.revision != revision:
            raise ValueError("Applied index release snapshot checksum mismatch")
        for version, checksum in release.get("baseline_migrations", {}).items():
            if history.get(version) != checksum:
                raise ValueError("Initial index snapshot does not match baseline migration history")
        if "baseline_migrations" not in release:
            path = next(p for p in files if p.name[:3] == release["migration"])
            if HEADER.findall(path.read_text()) != [(revision, release["sha256"])]:
                raise ValueError("Index release is not bound to its migration")
        selected = catalog
    if selected is None:
        raise ValueError("No applied index snapshot; migrate through 007 first")
    return selected
