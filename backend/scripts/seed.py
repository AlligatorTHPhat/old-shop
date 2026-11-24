"""Explicit plan/apply/resume for the shared bucket-v2 seeder."""

import argparse
import json
import os
from pathlib import Path

from app.buckets.db import one, transaction
from seeding.load import apply, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("plan")
    p.add_argument("--dataset", choices=["demo-v2", "contract-small", "benchmark-v2"], default="demo-v2")
    p.add_argument("--scale", type=int, default=1)
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("apply")
    p.add_argument("--plan", type=Path, required=True)
    p = commands.add_parser("resume")
    p.add_argument("--run-id", required=True)
    p = commands.add_parser("manifest")
    p.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "manifest":
        with transaction() as core:
            report = one(core, "SELECT manifest,verification FROM seed_manifest WHERE run_id=%s", (args.run_id,))
            if not report:
                raise ValueError("Run has not been verified")
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    elif args.command == "plan":
        document = plan(args.dataset, args.scale)
        with open(args.output, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            json.dump(document, stream, ensure_ascii=False, sort_keys=True, indent=2)
        print(
            json.dumps(
                {"run_id": document["run_id"], "dataset_hash": document["dataset_hash"], "plan": str(args.output)}
            )
        )
    else:
        if args.command == "apply":
            document = json.loads(args.plan.read_text())
        else:
            with transaction() as core:
                run = one(core, "SELECT plan FROM seed_runs WHERE run_id=%s", (args.run_id,))
                if not run:
                    raise ValueError("Unknown seed run")
                document = run["plan"]
        print(json.dumps(apply(document), ensure_ascii=False))


if __name__ == "__main__":
    main()
