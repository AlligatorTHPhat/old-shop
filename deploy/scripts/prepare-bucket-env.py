"""Create private credentials for the isolated oldshop-buckets stack; never overwrite."""

import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parents[1] / ".env.bucket"
with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
    for key in ("BUCKET_PG_PASSWORD", "BUCKET_MONGO_PASSWORD", "BUCKET_GRAPH_PASSWORD", "BUCKET_SECRET_KEY"):
        stream.write(f"{key}={secrets.token_hex(24)}\n")
    stream.write("BUCKET_DATASET=demo-v2\n")
print(f"Created {path.name}; credentials are not printed. Reuse on restart.")
