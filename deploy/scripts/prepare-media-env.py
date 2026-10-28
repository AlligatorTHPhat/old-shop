"""Add Day 3 application credentials while preserving all existing data-stack secrets."""

import argparse
import os
import secrets
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--enable-minio", action="store_true", help="Use only after bucket/seed setup succeeds")
args = parser.parse_args()
path = Path(__file__).resolve().parents[1] / ".env.data"
lines = path.read_text().splitlines()
values = dict(line.split("=", 1) for line in lines if line and not line.startswith("#") and "=" in line)
updates = {}
if not values.get("MINIO_APP_ACCESS_KEY"):
    updates["MINIO_APP_ACCESS_KEY"] = "oldshop_media"
if not values.get("MINIO_APP_SECRET_KEY"):
    updates["MINIO_APP_SECRET_KEY"] = secrets.token_hex(32)
if args.enable_minio:
    updates["STORAGE_BACKEND"] = "minio"
for key, value in updates.items():
    lines = [line for line in lines if not line.startswith(key + "=")]
    lines.append(f"{key}={value}")
fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".env.data-")
try:
    with os.fdopen(fd, "w") as target:
        target.write("\n".join(lines) + "\n")
    os.replace(temporary, path)
finally:
    Path(temporary).unlink(missing_ok=True)
print("Day 3 environment prepared; existing credentials retained; no secret values printed.")
