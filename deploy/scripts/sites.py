"""Operate two isolated PG16 sites. No dependency on the application's live database.

Only Docker Compose and Python's standard library are required on the host.
Passwords travel on stdin, never argv or evidence. Run from any directory.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "database/distributed"
DEPLOY = ROOT / "deploy/sites"
EVIDENCE = ROOT / "docs/evidence/distributed"
VERSION = 1


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def variables(values):
    if not values:
        return ""
    if any(not re.fullmatch(r"[a-z_]+", key) for key in values):
        raise ValueError("Invalid psql variable")
    return "SELECT " + ", ".join(f"{literal(value)} AS {key}" for key, value in values.items()) + " \\gset\n"


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare(path):
    values = {}
    for line in (DEPLOY / "env.example").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = secrets.token_hex(24) if value == "CHANGE_ME" else value
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    print(f"Created {path}; credentials not printed. Reuse this file on restart.")


def load_env(path):
    result = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    for site in "AB":
        name = result[f"SITE_{site}_DB_NAME"]
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name) or "lab" in name.lower():
            raise ValueError("Use an ordinary database name, e.g. oldshop_1 / oldshop_2")
        for role in ("ADMIN", "WRITER", "READER", "GLOBAL"):
            password = result[f"SITE_{site}_{role}_PASSWORD"]
            if len(password) < 16 or password == "CHANGE_ME" or any(c in password for c in "\r\n\x00"):
                raise ValueError("Set unique passwords of at least 16 characters in the env file")
    return result


def common_schema():
    """Build one schema from SQL-first sources; deliberately exclude every seed include.

    No modifications to migration history or to the baseline files. Historical
    migrations run on an empty-data schema, followed by the site extension.
    """
    paths = []
    for line in (ROOT / "database/init.sql").read_text().splitlines():
        if line.startswith("\\i "):
            path = line[3:].strip()
            if not path.startswith("03_seeds/"):
                paths.append(ROOT / "database" / path)
    migrations = sorted((ROOT / "database/04_migrations").glob("[0-9][0-9][0-9]_*.sql"))
    paths.extend(migrations)
    paths.append(SQL_DIR / "01_site_schema.sql")
    chunks = ["SET standard_conforming_strings = on;\n"]
    for path in paths:
        chunks.append(f"\n-- Source: {path.relative_to(ROOT)}\n{path.read_text()}\n")
    chunks.append("""CREATE TABLE schema_migrations (
        version varchar(3) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
        checksum char(64) NOT NULL);
    """)
    for path in migrations:
        chunks.append(
            "INSERT INTO schema_migrations(version,checksum) VALUES ("
            + literal(path.name.split("_", 1)[0])
            + ","
            + literal(hashlib.sha256(path.read_bytes()).hexdigest())
            + ");\n"
        )
    source = "".join(chunks)
    manifest = {
        "version": VERSION,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "files": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        "migrations": [path.name for path in migrations],
        "contains_application_seeds": False,
    }
    return source, manifest


def fixture(site):
    start = 1 if site == "A" else 2
    seller, outside_seller = (101, 103) if site == "A" else (202, 204)
    products, images = [], []
    for i in range(5):
        products.append(
            {
                "product_id": start + 2 * i,
                "seller_id": outside_seller if i == 4 else seller,
                "category_id": 1 if i % 2 == 0 else 2,
                "title": f"Site {site} product {i + 1}",
                "price": (i + 1) * (100 if site == "A" else 200),
                "quantity": 10,
                "status": 0 if i == 2 else 1,
                "is_deleted": i == 3,
                "created_at": "2026-10-01T00:00:00" if i == 4 else "2026-11-02T00:00:00",
                "site_id": site,
            }
        )
    for i, parent in enumerate([1, 1, 1, 1, 2, 2, 3, 4]):
        image_id = start + 2 * i
        images.append(
            {
                "image_id": image_id,
                "product_id": products[parent]["product_id"],
                "image_url": f"/media/products/site-{site.lower()}/fixture-{image_id}.png",
                "display_order": i,
                "is_primary": i in (0, 4, 6, 7),
            }
        )
    return {"products": products, "images": images}


def fixture_sql(site):
    data = fixture(site)
    chunks = [(SQL_DIR / "02_reference_fixture.sql").read_text()]
    for row in data["products"]:
        chunks.append(
            "INSERT INTO product (" + ",".join(row) + ") VALUES (" + ",".join(literal(v) for v in row.values()) + ");"
        )
    for row in data["images"]:
        chunks.append(
            "INSERT INTO product_image ("
            + ",".join(row)
            + ",uploaded_at) VALUES ("
            + ",".join(literal(v) for v in row.values())
            + ",'2026-11-02');"
        )
    for sequence, rows, key in (
        ("product_product_id_seq", data["products"], "product_id"),
        ("product_image_image_id_seq", data["images"], "image_id"),
    ):
        maximum = max(row[key] for row in rows)
        chunks.append(f"ALTER SEQUENCE {sequence} INCREMENT BY 2;")
        chunks.append(f"SELECT setval('{sequence}', {maximum}, true);")
    return "\n".join(chunks)


class Sites:
    def __init__(self, env_path=DEPLOY / ".env", project="oldshop-sites", site="both"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
            raise ValueError("Invalid Compose project")
        self.env_path = Path(env_path).resolve()
        self.env = load_env(self.env_path)
        self.project = project
        self.selected = "AB" if site == "both" else site
        self.compose = ["docker", "compose", "-p", project, "--env-file", str(self.env_path)]
        for key in self.selected:
            self.compose += ["-f", str(DEPLOY / f"compose.site-{key.lower()}.yml")]
        if "A" in self.selected:
            self.compose += ["-f", str(DEPLOY / "compose.catalog.yml")]

    def redact(self, value):
        for key, password in self.env.items():
            if key.endswith("_PASSWORD"):
                value = value.replace(password, "[REDACTED]")
        return value

    def run(self, args, input_text=None, check=True, timeout=180):
        result = subprocess.run(
            self.compose + args,
            input=input_text,
            text=True,
            cwd=ROOT,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, **self.env},
        )
        result.stdout = self.redact(result.stdout)
        result.stderr = self.redact(result.stderr)
        if check and result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr[-4000:]}")
        return result

    def sql(
        self,
        site,
        statement,
        *,
        role="admin",
        check=True,
        values=None,
        database=None,
        connect_host="127.0.0.1",
        connect_port="5432",
        password_site=None,
    ):
        role_name = {"admin": "site_admin", "writer": "site_writer", "reader": "b_reader", "global": "global_reader"}[
            role
        ]
        password_key = {"admin": "ADMIN", "writer": "WRITER", "reader": "READER", "global": "GLOBAL"}[role]
        password = self.env[f"SITE_{password_site or site}_{password_key}_PASSWORD"]
        db = database or self.env[f"SITE_{site}_DB_NAME"]
        # read consumes just the password line; psql consumes the remaining SQL stdin.
        command = [
            "exec",
            "-T",
            f"pg-{site.lower()}",
            "sh",
            "-c",
            "IFS= read -r PGPASSWORD; export PGPASSWORD; export PGCONNECT_TIMEOUT=3; "
            'export PGOPTIONS="-c statement_timeout=10000 -c lock_timeout=3000"; exec "$@"',
            "sh",
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "VERBOSITY=verbose",
            "-h",
            connect_host,
            "-p",
            str(connect_port),
            "-U",
            role_name,
            "-d",
            db,
        ]
        payload = password + "\n" + variables(values) + statement + "\n"
        return self.run(command, payload, check=check)

    def query(self, site, statement, **kwargs):
        result = self.sql(
            site,
            "SELECT COALESCE(json_agg(row_to_json(r)), '[]'::json) FROM (" + statement.rstrip().rstrip(";") + ") r;",
            **kwargs,
        )
        return json.loads(result.stdout)

    def bootstrap(self):
        source, manifest = common_schema()
        for site in self.selected:
            present = self.query(site, "SELECT to_regclass('public.distributed_installation')::text AS marker")[0]
            if present["marker"]:
                installed = self.query(site, "SELECT * FROM distributed_installation")[0]
                identity = self.query(site, "SELECT site_id FROM site_config")[0]["site_id"]
                if (
                    installed["source_sha256"] != manifest["source_sha256"]
                    or installed["version"] != VERSION
                    or installed["fixture_version"] != 1
                    or identity != site
                ):
                    raise RuntimeError("Existing site's source/identity differs; review rather than overwrite")
                print(f"Site {site}: existing installation verified; no fixtures reloaded")
                continue
            occupied = self.query(site, "SELECT count(*) AS n FROM pg_tables WHERE schemaname='public'")[0]["n"]
            if occupied:
                raise RuntimeError("Refusing bootstrap into an existing application schema")
            remainder = 1 if site == "A" else 0
            role_sql = ""
            for name, key in (("site_writer", "WRITER"), ("b_reader", "READER"), ("global_reader", "GLOBAL")):
                pw = self.env[f"SITE_{site}_{key}_PASSWORD"]
                role_sql += f"CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {literal(pw)};\n"
            sql = (
                "BEGIN;\nSET LOCAL statement_timeout='120s';\n"
                + source
                + f"INSERT INTO site_config VALUES (true, '{site}', {remainder});\n"
                + f"INSERT INTO distributed_installation VALUES (true, {VERSION}, "
                + literal(manifest["source_sha256"])
                + ", 1);\n"
                + fixture_sql(site)
                + "\n"
                + role_sql
                + (SQL_DIR / "03_permissions.sql").read_text()
                + "\nCOMMIT;"
            )
            self.sql(site, sql, values={"target_db": self.env[f"SITE_{site}_DB_NAME"]})
            print(f"Site {site}: schema 001–007, ownership rules and synthetic fixtures installed")
        self.configure_access()
        save_json(EVIDENCE / "source_manifest.json", manifest)
        save_json(SQL_DIR / "fixture_manifest.json", {"version": 1, "A": fixture("A"), "B": fixture("B")})

    def configure_access(self):
        network = ipaddress.ip_network(self.env["SITES_SUBNET"])
        gateway = str(network.network_address + 1) + "/32"
        for site in self.selected:
            db = self.env[f"SITE_{site}_DB_NAME"]
            source = self.env.get(f"SITE_{site}_READER_SOURCE_CIDR", self.env["SITE_A_VIRTUAL_IP"] + "/32")
            source = str(ipaddress.ip_network(source, strict=False))
            api_source = self.env.get("CATALOGUE_VIRTUAL_IP", "172.29.82.20") + "/32"
            api_source = str(ipaddress.ip_network(api_source, strict=False))
            rules = ["local all site_admin trust", "local all all reject"]
            for address in ("127.0.0.1/32", gateway):
                rules.append(f"host {db} all {address} scram-sha-256")
            rules += [
                f"host {db} b_reader {source} scram-sha-256",
                f"host {db} global_reader {api_source} scram-sha-256",
                "host all all 0.0.0.0/0 reject",
                "host all all ::/0 reject",
            ]
            self.run(
                [
                    "exec",
                    "-T",
                    f"pg-{site.lower()}",
                    "sh",
                    "-c",
                    'umask 077; cat > "$PGDATA/pg_hba.conf"; chown postgres:postgres "$PGDATA/pg_hba.conf"',
                ],
                "\n".join(rules) + "\n",
            )
            valid = self.query(site, "SELECT count(*) AS n FROM pg_hba_file_rules WHERE error IS NOT NULL")[0]["n"]
            if valid:
                raise RuntimeError("Invalid HBA rules; inspect the isolated site's configuration")
            self.sql(site, "SELECT pg_reload_conf();")
        print("HBA restricted to local administration, the host gateway, the catalogue and the FDW reader source")

    def configure_fdw(self):
        if "A" not in self.selected:
            raise ValueError("FDW is configured at A")
        existing = self.query("A", "SELECT srvname FROM pg_foreign_server WHERE srvname='server_b'")
        params = {
            "b_host": self.env["SITE_B_FDW_HOST"],
            "b_port": self.env["SITE_B_FDW_PORT"],
            "b_db": self.env["SITE_B_DB_NAME"],
            "reader_pw": self.env["SITE_B_READER_PASSWORD"],
            "admin_role": "site_admin",
        }
        if existing:
            self.sql(
                "A",
                """BEGIN;
                ALTER SERVER server_b OPTIONS (SET host :'b_host', SET port :'b_port', SET dbname :'b_db');
                ALTER USER MAPPING FOR site_admin SERVER server_b OPTIONS (SET password :'reader_pw');
                COMMIT;""",
                values=params,
            )
        else:
            self.sql(
                "A",
                "BEGIN;\n"
                + (SQL_DIR / "04_fdw.sql").read_text()
                + "\n"
                + (SQL_DIR / "05_global_views.sql").read_text()
                + "\nCOMMIT;",
                values=params,
            )
        self.sql("A", "BEGIN;\n" + (SQL_DIR / "05_global_views.sql").read_text() + "\nCOMMIT;")
        result = self.query("A", "SELECT site_id FROM site_b.site_identity")
        if result != [{"site_id": "B"}]:
            # site_identity has a second column, but the explicit SELECT above only returns site_id.
            raise RuntimeError("Foreign server does not identify as B")
        print("FDW A → B configured and remote site identity checked")

    def inventory(self):
        return {
            "physical_hosts_verified": False,
            "topology": "two independent PostgreSQL containers on one Docker host",
            "project": self.project,
            "sites": {
                site: self.query(
                    site,
                    """SELECT current_database() AS database, current_user AS role,
                    inet_server_addr()::text AS server_address, version() AS postgres,
                    (SELECT site_id FROM site_config) AS site_id,
                    (SELECT count(*) FROM product) AS products,
                    (SELECT count(*) FROM product_image) AS images,
                    (SELECT array_agg(version ORDER BY version) FROM schema_migrations) AS migrations""",
                )[0]
                for site in self.selected
            },
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "prepare",
            "up",
            "bootstrap",
            "access",
            "fdw",
            "status",
            "verify",
            "catalogue",
            "verify-api",
            "stop",
            "down",
        ],
    )
    parser.add_argument("--env", type=Path, default=DEPLOY / ".env")
    parser.add_argument("--project", default="oldshop-sites")
    parser.add_argument("--site", choices=["A", "B", "both"], default="both")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.env)
        return
    sites = Sites(args.env, args.project, args.site)
    if args.command == "up":
        sites.run(["up", "-d", "--wait", "--wait-timeout", "90"])
        print("Independent PostgreSQL sites are healthy")
    elif args.command == "bootstrap":
        sites.bootstrap()
    elif args.command == "fdw":
        sites.configure_fdw()
    elif args.command == "access":
        sites.configure_access()
    elif args.command == "status":
        inventory = sites.inventory()
        save_json(EVIDENCE / "inventory.json", inventory)
        print(json.dumps(inventory, ensure_ascii=False, indent=2))
    elif args.command == "verify":
        from verify_sites import verify

        verify(sites)
    elif args.command == "catalogue":
        if "A" not in sites.selected:
            raise ValueError("The global catalogue gateway runs at site A")
        sites.run(["--profile", "catalogue", "up", "-d", "--wait", "--wait-timeout", "90", "catalogue"])
        print("Read-only catalogue: http://127.0.0.1:" + sites.env.get("CATALOGUE_PORT", "56480") + "/docs")
    elif args.command == "verify-api":
        from verify_catalogue import verify_api

        verify_api(sites)
    else:
        profile = ["--profile", "catalogue"] if "A" in sites.selected else []
        sites.run([*profile, args.command])  # No volume deletion, ever, through this command.
        print("Sites stopped; persistent volumes retained")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
