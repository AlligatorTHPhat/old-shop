"""Run indexing benchmarks/regressions in an isolated PG/Mongo8/MinIO Compose project.

No application credentials are read. --state can resume the private test stack;
--cleanup removes only the project recorded by this runner. Evidence has no secrets.
"""

import argparse
import json
import os
import secrets
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]


def run(command, *, capture=False, output=None):
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else output,
    )
    return result.stdout


def create(state_file, evidence):
    if state_file.exists():
        raise RuntimeError("State exists; use --reuse or a fresh state path")
    private = Path(tempfile.mkdtemp(prefix="oldshop-indexing-v2-"))
    project = "oldshop-indexing-v2-" + secrets.token_hex(4)
    values = {}
    for line in (ROOT / "deploy/.env.data.example").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = (
                secrets.token_hex(384 if key == "MONGO_KEYFILE" else 32)
                if value == "CHANGE_ME"
                else value
            )
    values.update(MONGO_IMAGE="mongo:8.0.32", STORAGE_BACKEND="minio")
    for key in (
        "PG_PRIMARY_PORT",
        "PG_REPLICA_PORT",
        "BACKEND_PORT",
        "FRONTEND_PORT",
        "MINIO_API_PORT",
        "MINIO_CONSOLE_PORT",
    ):
        values[key] = "0"
    env = private / ".env"
    env.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    env.chmod(0o600)
    evidence.mkdir(parents=True, exist_ok=True)
    state = {
        "project": project,
        "env": str(env),
        "runner": project + "-runner",
        "evidence": str(evidence),
        "stamp": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y%m%d_%H%M%S"),
    }
    state_file.write_text(json.dumps(state))
    state_file.chmod(0o600)
    return state


def compose(state):
    if not state["project"].startswith("oldshop-indexing-v2-"):
        raise RuntimeError("Not an indexing-v2 test project")
    return [
        "docker",
        "compose",
        "-p",
        state["project"],
        "--env-file",
        state["env"],
        "-f",
        str(ROOT / "deploy/docker-compose.distributed.yml"),
    ]


def execute(state, args, *, database=None, output=None):
    command = ["docker", "exec"]
    if database:
        if not database.startswith(("indexing_v2_", "day5_test_")):
            raise RuntimeError("Refusing a non-test database")
        command += [
            "-e",
            "DB_NAME=" + database,
            "-e",
            "MONGO_DB=" + database,
            "-e",
            "MEDIA_DIR=/tmp/" + database + "-media",
        ]
    command += [state["runner"], "env", "-u", "PROMETHEUS_MULTIPROC_DIR", *args]
    return run(command, output=output)


def setup(state):
    dc = compose(state)
    run(
        dc
        + [
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "240",
            "pg-primary",
            "mongo1",
            "minio",
        ]
    )
    for job in ("mongo-init", "minio-init"):
        run(dc + ["run", "--rm", "--no-deps", job])
    command = dc + [
        "run",
        "-d",
        "--no-deps",
        "--name",
        state["runner"],
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "PYTHONUSERBASE=/tmp/indexing-python",
        "-e",
        "ENVIRONMENT=test",
        "-e",
        "MEDIA_DIR=/tmp/indexing-media",
        "-e",
        "DAY3_INTEGRATION=1",
        "-e",
        "DAY5_INTEGRATION=1",
        "-e",
        "DAY6_INTEGRATION=1",
        "-e",
        "GAS_WEBHOOK_URL=",
        "-e",
        "LOG_LEVEL=WARNING",
    ]
    for source, target in (
        (ROOT / "backend/app", "/app/app"),
        (ROOT / "backend/etl", "/app/etl"),
        (ROOT / "backend/scripts", "/app/scripts"),
        (ROOT / "backend/tests", "/app/tests"),
        (ROOT / "backend/pytest.ini", "/app/pytest.ini"),
        (ROOT / "backend/requirements-dev.lock", "/tmp/dev.lock"),
        (ROOT / "database", "/opt/database"),
    ):
        command += ["-v", f"{source}:{target}:ro"]
    command += [
        "-v",
        f"{state['evidence']}:/evidence",
        "--entrypoint",
        "sleep",
        "etl-test",
        "infinity",
    ]
    run(command)
    # Runtime dependencies are already in the image; install hash-locked test tools only if missing.
    execute(
        state,
        [
            "python",
            "-m",
            "pip",
            "install",
            "--user",
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "-q",
            "-r",
            "/tmp/dev.lock",
        ],
    )


def cleanup(state, state_file):
    subprocess.run(
        ["docker", "rm", "-f", "-v", state["runner"]],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    run(compose(state) + ["down", "-v", "--remove-orphans"])
    env = Path(state["env"])
    env.unlink(missing_ok=True)
    env.parent.rmdir()
    state_file.unlink(missing_ok=True)


def tests(state):
    evidence = Path(state["evidence"])
    selections = {
        "regression": [
            "tests",
            "--ignore=tests/test_day5_etl.py",
            "--ignore=tests/test_day6_integration.py",
        ],
        "etl": ["tests/test_day5_etl.py"],
        "api": ["tests/test_day6_integration.py"],
    }
    for phase, selection in selections.items():
        database = "day5_test_indexing_" + state["stamp"] + "_" + phase
        execute(state, ["python", "-m", "scripts.init_db"], database=database)
        execute(state, ["python", "-m", "scripts.init_mongo"], database=database)
        command = [
            "python",
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            *selection,
        ]
        with (evidence / f"tests_{phase}.txt").open("w") as output:
            # Local-storage regression remains meaningful; hybrid integration uses real MinIO.
            if phase == "regression":
                command = ["env", "STORAGE_BACKEND=local", *command]
            execute(state, command, database=database, output=output)
        print(f"PASS phase={phase}", flush=True)
    restore_rehearsal(state)
    with (evidence / "lint.txt").open("w") as output:
        execute(
            state,
            [
                "python",
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "scripts/benchmark_indexing_v2.py",
                "scripts/benchmark_mongo_indexing_v2.py",
                "scripts/benchmark_indexing_selected.py",
                "scripts/verify_indexing_v2.py",
                "tests/test_indexing_v2.py",
            ],
            output=output,
        )


def restore_rehearsal(state):
    """Rehearse dump/restore only inside this disposable Compose project."""
    evidence = Path(state["evidence"])
    source = "day5_test_indexing_" + state["stamp"] + "_backup"
    restored = source + "_restored"
    execute(state, ["python", "-m", "scripts.init_db"], database=source)
    execute(
        state,
        [
            "python",
            "-m",
            "scripts.verify_day4",
            "--output",
            "/evidence/restore_source.json",
        ],
        database=source,
    )
    dc = compose(state)
    pg = dc + ["exec", "-T", "pg-primary", "sh", "-c"]
    run(pg + ['createdb -U "$POSTGRES_USER" "$1"', "sh", restored])
    try:
        with tempfile.TemporaryFile() as backup:
            subprocess.run(
                pg + ['pg_dump -U "$POSTGRES_USER" -d "$1" -Fc', "sh", source],
                check=True,
                stdout=backup,
            )
            backup.seek(0)
            subprocess.run(
                pg
                + [
                    'pg_restore --exit-on-error -U "$POSTGRES_USER" -d "$1"',
                    "sh",
                    restored,
                ],
                check=True,
                stdin=backup,
            )
        execute(
            state,
            [
                "python",
                "-m",
                "scripts.verify_day4",
                "--compare",
                "/evidence/restore_source.json",
            ],
            database=restored,
        )
        with (evidence / "restore_postflight.json").open("w") as output:
            execute(
                state,
                ["python", "-m", "scripts.verify_indexing_v2"],
                database=restored,
                output=output,
            )
        (evidence / "restore_rehearsal.json").write_text(
            json.dumps(
                {
                    "result": "PASS",
                    "custom_dump_restored": True,
                    "source_digest_equal": True,
                    "postflight_007": True,
                }
            )
            + "\n"
        )
    finally:
        run(pg + ['dropdb -U "$POSTGRES_USER" "$1"', "sh", restored])
        run(pg + ['dropdb -U "$POSTGRES_USER" "$1"', "sh", source])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("prepare", "benchmarks", "tests"), default="benchmarks"
    )
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep only the isolated test stack for another phase",
    )
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    state_file = args.state.resolve()
    state = (
        json.loads(state_file.read_text())
        if args.reuse or args.cleanup
        else create(state_file, evidence)
    )
    try:
        if args.cleanup:
            return
        if not args.reuse:
            setup(state)
        if args.phase == "benchmarks":
            database = "indexing_v2_" + state["stamp"]
            execute(
                state,
                [
                    "python",
                    "-m",
                    "scripts.benchmark_indexing_v2",
                    "--output",
                    "/evidence/pg",
                ],
                database=database,
            )
            execute(
                state,
                [
                    "python",
                    "-m",
                    "scripts.benchmark_mongo_indexing_v2",
                    "--output",
                    "/evidence/mongo",
                ],
                database=database,
            )
            execute(
                state,
                [
                    "python",
                    "-m",
                    "scripts.benchmark_indexing_selected",
                    "--output",
                    "/evidence/selected",
                ],
                database=database,
            )
            execute(state, ["python", "-m", "scripts.init_mongo"], database=database)
            with (Path(state["evidence"]) / "postflight.json").open("w") as output:
                execute(
                    state,
                    ["python", "-m", "scripts.verify_indexing_v2", "--mongo"],
                    database=database,
                    output=output,
                )
            execute(
                state,
                [
                    "python",
                    "-m",
                    "scripts.benchmark_indexing_selected",
                    "--approved-write-clone",
                    "--output",
                    "/evidence/approved_writes",
                ],
                database=database,
            )
        elif args.phase == "tests":
            tests(state)
        print(
            json.dumps(
                {
                    "project": state["project"],
                    "phase": args.phase,
                    "evidence": state["evidence"],
                }
            ),
            flush=True,
        )
    finally:
        if args.cleanup or not args.keep:
            cleanup(state, state_file)


if __name__ == "__main__":
    main()
