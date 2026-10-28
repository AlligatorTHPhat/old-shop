"""Generate local Day 2 credentials without overwriting an existing environment."""

import os
import secrets
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
destination = DEPLOY / ".env.data"
template = (DEPLOY / ".env.data.example").read_text(encoding="utf-8")
lines = []
for line in template.splitlines():
    if line.endswith("=CHANGE_ME"):
        key = line.split("=", 1)[0]
        value = secrets.token_hex(384 if key == "MONGO_KEYFILE" else 32)
        line = f"{key}={value}"
    lines.append(line)
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as target:
    target.write("\n".join(lines) + "\n")
print(f"Created {destination}; existing credentials are never overwritten.")
