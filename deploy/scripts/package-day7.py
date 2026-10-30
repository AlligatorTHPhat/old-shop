"""Package a clean, locally tagged Day 7 source tree and explicit generated deliverables.

No network/push. Runtime env, backups, Git metadata and raw browser recordings are excluded.
The manifest hashes every payload file; the archive checksum is written beside the ZIP.
"""

import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "docs/report/generated"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--tag", default="v0.7.0-data-upgrade")
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", args.tag):
    raise SystemExit("Invalid release tag")


def git(*argv):
    return subprocess.check_output(["git", *argv], cwd=ROOT)


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


commit = git("rev-parse", "HEAD").decode().strip()
if git("rev-parse", args.tag + "^{commit}").decode().strip() != commit:
    raise SystemExit("Release tag must resolve to HEAD")
if git("status", "--porcelain", "--untracked-files=normal").strip():
    raise SystemExit("Commit source/evidence first; package requires a clean worktree")

rehearsal = json.loads((ROOT / "docs/evidence/day7_rehearsal.json").read_text())
validation = json.loads(
    (ROOT / "docs/evidence/day7_output_validation.json").read_text()
)
assert rehearsal["result"] == validation["result"] == "PASS"
assert 300 <= rehearsal["video_seconds"] <= 420
assert (
    json.loads((ROOT / "docs/evidence/day7_stack.json").read_text())["result"] == "PASS"
)

# Compare bytes against real local secrets without logging their values. Seed credentials in
# SQL/examples are intentionally part of this educational source, not private runtime secrets.
private_values = []
for env_path in (ROOT / "deploy/.env.data", ROOT / "backend/.env", ROOT / ".env"):
    if not env_path.exists():
        continue
    for line in env_path.read_text().splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        if (
            len(value) >= 24
            and re.search(r"PASSWORD|SECRET|TOKEN|KEYFILE", key)
            and value != "CHANGE_ME"
        ):
            private_values.append(value.encode())


def inspect(path, blob):
    if any(value in blob for value in private_values):
        raise SystemExit(f"Private runtime value detected in {path}; value suppressed")
    if path.endswith((".docx", ".pptx")):
        with zipfile.ZipFile(io.BytesIO(blob)) as office:
            for name in office.namelist():
                if name.endswith((".xml", ".rels")) and any(
                    value in office.read(name) for value in private_values
                ):
                    raise SystemExit(
                        f"Private runtime value inside {path}; value suppressed"
                    )


payload = {}
for raw in git("ls-files", "-z").split(b"\0"):
    if not raw:
        continue
    name = raw.decode()
    path = Path(name)
    blocked = {".git", ".aws", "node_modules", "__pycache__", "backups", "ml_artifacts"}
    if blocked.intersection(path.parts) or (
        path.name.startswith(".env") and not path.name.endswith(".example")
    ):
        raise SystemExit(f"Forbidden tracked runtime path: {name}")
    if path.suffix in {".dump", ".pem", ".key", ".joblib", ".zip"}:
        raise SystemExit(f"Forbidden tracked binary: {name}")
    if (ROOT / path).is_symlink():
        raise SystemExit(f"Symlink requires explicit review: {name}")
    blob = git("show", "HEAD:" + name)
    inspect(name, blob)
    payload[name] = blob

deliverables = [
    "oldshop_report.docx",
    "oldshop_report.pdf",
    "oldshop_slides.pptx",
    "oldshop_slides.pdf",
    "oldshop_demo.mp4",
    "oldshop_demo.srt",
]
for name in deliverables:
    blob = (GENERATED / name).read_bytes()
    assert len(blob) > 100, name
    assert digest(blob) == validation["artifact_hashes"][name]["sha256"], (
        f"Revalidate changed artifact: {name}"
    )
    relative = "docs/report/generated/" + name
    inspect(relative, blob)
    payload[relative] = blob

manifest = {
    "tag": args.tag,
    "commit": commit,
    "created_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
    "scope": "Single-host local MVP; Mongo7 tested, Mongo8 and remote CI not verified",
    "file_count": len(payload),
    "files": [
        {"path": p, "bytes": len(b), "sha256": digest(b)}
        for p, b in sorted(payload.items())
    ],
    "exclusions": [
        ".git",
        "runtime .env",
        "backups/dumps",
        "volumes",
        "raw_video",
        "node_modules",
    ],
    "manifest_note": "Manifest hashes payload files, not itself. ZIP checksum is outside archive.",
    "private_values_checked": len(private_values),
}
out = ROOT / "dist/releases"
out.mkdir(parents=True, exist_ok=True)
archive_path = out / f"oldshop-{args.tag}.zip"
prefix = "oldshop-day7/"
with zipfile.ZipFile(
    archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6
) as archive:
    for path, blob in sorted(payload.items()):
        archive.writestr(prefix + path, blob)
    archive.writestr(
        prefix + "RELEASE_MANIFEST.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )

with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == len(payload) + 1
    stored = json.loads(archive.read(prefix + "RELEASE_MANIFEST.json"))
    for entry in stored["files"]:
        assert digest(archive.read(prefix + entry["path"])) == entry["sha256"], entry[
            "path"
        ]
checksum = digest(archive_path.read_bytes())
archive_path.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive_path.name}\n")
result = {
    "result": "PASS",
    "archive": str(archive_path.relative_to(ROOT)),
    "bytes": archive_path.stat().st_size,
    "sha256": checksum,
    "payload_files": len(payload),
    "commit": commit,
    "tag": args.tag,
    "crc_and_all_file_hashes": "PASS",
    "runtime_secret_scan": "PASS",
}
(GENERATED / "packaging_validation.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(result, indent=2))
