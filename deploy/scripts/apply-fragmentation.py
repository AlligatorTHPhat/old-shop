"""Upgrade the isolated catalogue sites after backup/restore rehearsal.

No reseed; no operation on the commerce database. Default credentials stay in the
existing ignored env file. Backups contain data and must remain private.
"""

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path

from sites import DEPLOY, ROOT, Sites, save_json

TABLES = [
    "product",
    "product_image",
    "category",
    "seller_site",
    "user_core",
    "user_profile",
    "user_secret",
    "user_wallet",
]


def snapshot(sites, site, database=None):
    return {
        table: sites.query(
            site,
            "SELECT count(*) AS rows,md5(coalesce(string_agg(to_jsonb(t)::text,E'\\n' "
            f"ORDER BY to_jsonb(t)::text),'')) AS digest FROM {table} t",
            **({"database": database, "connect_host": "/var/run/postgresql"} if database else {}),
        )[0]
        for table in TABLES
    }


def backup_and_restore(sites, site, directory, expected):
    filename = directory / f"site_{site}.dump"
    env = {**os.environ, **sites.env}
    command = sites.compose + ["exec", "-T", f"pg-{site.lower()}"]
    with filename.open("wb") as output:
        subprocess.run(
            command + ["pg_dump", "-U", "site_admin", "-Fc", "-d", sites.env[f"SITE_{site}_DB_NAME"]],
            stdout=output,
            stderr=subprocess.PIPE,
            check=True,
            cwd=ROOT,
            env=env,
        )
    restore = "fragment_restore_" + datetime.now().strftime("%H%M%S") + site.lower()
    sites.run(["exec", "-T", f"pg-{site.lower()}", "createdb", "-U", "site_admin", restore])
    try:
        with filename.open("rb") as stream:
            subprocess.run(
                command + ["pg_restore", "-U", "site_admin", "--exit-on-error", "-d", restore],
                stdin=stream,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
                cwd=ROOT,
                env=env,
            )
        if snapshot(sites, site, restore) != expected:
            raise RuntimeError("Restore rehearsal data differs")
    finally:
        sites.run(["exec", "-T", f"pg-{site.lower()}", "dropdb", "-U", "site_admin", restore])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["apply", "rollback-routing"])
    parser.add_argument("--env", type=Path, default=DEPLOY / ".env")
    parser.add_argument("--project", default="oldshop-sites")
    args = parser.parse_args()
    sites = Sites(args.env, args.project)
    if args.command == "rollback-routing":
        sites.env["DISTRIBUTED_CATALOG_ROUTING"] = "0"
    else:
        if sites.env["SITE_A_VIRTUAL_IP"] == sites.env["SITE_B_VIRTUAL_IP"] or sites.env["SITE_B_FDW_HOST"] not in (
            "pg-b",
            sites.env["SITE_B_VIRTUAL_IP"],
        ):
            raise ValueError("This runner requires two local sites; use per-host migrations for a VPN topology")
        if sites.query("A", "SELECT site_id FROM site_b.site_identity") != [{"site_id": "B"}]:
            raise ValueError("Existing FDW target is unavailable or is not site B")
        evidence = ROOT / "docs/evidence/fragmentation_indexing"
        plan = sites.upgrade(apply=False)
        directory = ROOT / "deploy/backups" / ("fragmentation_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        directory.mkdir(parents=True, mode=0o700)
        before = {s: snapshot(sites, s) for s in "AB"}
        for site in "AB":
            backup_and_restore(sites, site, directory, before[site])
        print("Backups and restore rehearsal: PASS", flush=True)
        applied = sites.upgrade()
        sites.configure_fdw(preserve_endpoint=True)
        after = {s: snapshot(sites, s) for s in "AB"}
        if before != after:
            raise RuntimeError("Source rows changed during upgrade; review backups before reopening")
        save_json(
            evidence / "rollout.json",
            {
                "result": "PASS",
                "backup_restore_verified": True,
                "backup_directory": str(directory.relative_to(ROOT)),
                "source_rows_unchanged": True,
                "before": before,
                "after": after,
                "plan": plan,
                "upgrade": applied,
            },
        )
    sites.run(["--profile", "catalogue", "up", "-d", "--no-deps", "--force-recreate", "catalogue"])
    print("Catalogue restart requested; verify /ready and HTTP outage checks", flush=True)


if __name__ == "__main__":
    main()
