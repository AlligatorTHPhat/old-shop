"""Build and test in an isolated Compose project; never stop the user's data stack."""

import argparse
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mongo-image", default="mongo:8.0.32")
parser.add_argument("--skip-build", action="store_true")
parser.add_argument(
    "--skip-regression",
    action="store_true",
    help="Recheck ETL and Day 6 after a worker change",
)
parser.add_argument(
    "--app-only",
    action="store_true",
    help="Recheck changed Day 6 API/worker and outage scenarios",
)
parser.add_argument(
    "--evidence", type=Path, default=ROOT / "docs/evidence/day6_failover.json"
)
args = parser.parse_args()
project = "oldshop-day6-test-" + secrets.token_hex(4)
stamp = time.strftime("%Y%m%d%H%M%S")


def run(command, capture=False):
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    ).stdout


if not args.skip_build:
    run(
        [
            "docker",
            "build",
            "-t",
            "oldshop-data-backend:day6",
            "-f",
            "backend/Dockerfile",
            ".",
        ]
    )
    run(["docker", "build", "-t", "oldshop-data-frontend:day6", "frontend"])

with tempfile.TemporaryDirectory(prefix="oldshop-day6-") as temp:
    env = Path(temp) / ".env"
    values = {}
    for line in (ROOT / "deploy/.env.data.example").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = (
                secrets.token_hex(384 if key == "MONGO_KEYFILE" else 32)
                if value == "CHANGE_ME"
                else value
            )
    values.update(
        MONGO_IMAGE=args.mongo_image,
        BACKEND_IMAGE="oldshop-data-backend:day6",
        FRONTEND_IMAGE="oldshop-data-frontend:day6",
        STORAGE_BACKEND="minio",
    )
    for key in (
        "PG_PRIMARY_PORT",
        "PG_REPLICA_PORT",
        "BACKEND_PORT",
        "FRONTEND_PORT",
        "MINIO_API_PORT",
        "MINIO_CONSOLE_PORT",
    ):
        values[key] = (
            "0"  # Docker allocates loopback-only ports; no collision with oldshop-data.
        )
    env.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    os.chmod(env, 0o600)
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "--env-file",
        str(env),
        "-f",
        str(ROOT / "deploy/docker-compose.distributed.yml"),
        "--profile",
        "resilience",
    ]
    try:
        run(
            compose
            + [
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "240",
                "pg-primary",
                "pg-replica",
                "mongo1",
                "mongo2",
                "mongo3",
                "minio",
            ]
        )
        for job in ("mongo-init", "mongo-expand", "minio-init"):
            run(compose + ["run", "--rm", "--no-deps", job])
        phases = (
            ("app",)
            if args.app_only
            else (
                ("etl", "app") if args.skip_regression else ("regression", "etl", "app")
            )
        )
        for phase in phases:
            db = f"day5_test_{stamp}_{phase}"
            job = compose + [
                "run",
                "--rm",
                "--no-deps",
                "-e",
                f"DB_NAME={db}",
                "-e",
                f"MONGO_DB={db}",
                "-e",
                "MEDIA_DIR=/tmp/day6-media",
            ]
            run(job + ["--entrypoint", "python", "etl-test", "-m", "scripts.init_db"])
            run(
                job + ["--entrypoint", "python", "etl-test", "-m", "scripts.init_mongo"]
            )
            selection = {
                "regression": [
                    "tests",
                    "--ignore=tests/test_day5_etl.py",
                    "--ignore=tests/test_day6_integration.py",
                ],
                "etl": ["tests/test_day5_etl.py"],
                "app": ["tests/test_day6_integration.py"],
            }[phase]
            run(
                job
                + [
                    "-e",
                    f"STORAGE_BACKEND={'local' if phase == 'regression' else 'minio'}",
                    "-e",
                    "DAY3_INTEGRATION=1",
                    "-e",
                    "DAY5_INTEGRATION=1",
                    "-e",
                    "DAY6_INTEGRATION=1",
                    "-e",
                    "DEBUG=false",
                    "-e",
                    "PYTHONUSERBASE=/tmp/day6-py",
                    "-v",
                    f"{ROOT}/backend/tests:/app/tests:ro",
                    "-v",
                    f"{ROOT}/backend/pytest.ini:/app/pytest.ini:ro",
                    "-v",
                    f"{ROOT}/backend/requirements-dev.lock:/tmp/dev.lock:ro",
                    "--entrypoint",
                    "sh",
                    "etl-test",
                    "-c",
                    (
                        "mkdir -p /tmp/prometheus && python -m pip install --user --require-hashes --only-binary :all: -q "
                        '--no-warn-script-location -r /tmp/dev.lock && python -m pytest -o addopts="" -p no:cacheprovider "$@"'
                    ),
                    "sh",
                    *selection,
                ]
            )
            print(f"PASS phase={phase} database={db}", flush=True)
        run(compose + ["up", "-d", "--wait", "--wait-timeout", "240"])
        run(compose + ["restart", "frontend"])
        evidence = {
            "project": project,
            "mongo_image": args.mongo_image,
            "isolated": True,
            "scenarios": [],
        }

        def probe(scenario, mode="normal"):
            deadline = time.monotonic() + 60
            command = compose + [
                "exec",
                "-T",
                "backend",
                "python",
                "-m",
                "scripts.verify_day6",
                "--mode",
                mode,
                "--authenticated",
            ]
            while True:
                try:
                    output = run(command, capture=True)
                    break
                except subprocess.CalledProcessError:
                    if mode != "normal" or time.monotonic() >= deadline:
                        raise
                    # A pingable mongod is not necessarily an elected, queryable replica set.
                    time.sleep(2)
            result = json.loads(output)
            evidence["scenarios"].append({"scenario": scenario, **result})
            print(json.dumps({"scenario": scenario, **result}), flush=True)

        probe("baseline")
        for service in ("mongo2", "pg-replica", "minio"):
            run(compose + ["stop", service])
            try:
                probe(
                    f"{service}_stopped",
                    "minio-down" if service == "minio" else "normal",
                )
            finally:
                run(
                    compose
                    + [
                        "up",
                        "-d",
                        "--no-deps",
                        "--wait",
                        "--wait-timeout",
                        "120",
                        service,
                    ]
                )
            probe(f"{service}_recovered")
        # Total Mongo outage proves detail fallback and fail-closed filters on real sockets.
        run(compose + ["stop", "mongo1", "mongo2", "mongo3"])
        try:
            probe("mongo_unavailable", "mongo-down")
        finally:
            run(
                compose
                + [
                    "up",
                    "-d",
                    "--no-deps",
                    "--wait",
                    "--wait-timeout",
                    "180",
                    "mongo1",
                    "mongo2",
                    "mongo3",
                ]
            )
        probe("mongo_recovered")
        evidence["result"] = "PASS"
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        )
    finally:
        # This project and all of its disposable volumes were created by this invocation.
        subprocess.run(
            compose + ["down", "--volumes", "--remove-orphans"], cwd=ROOT, check=False
        )
