"""Disposable two-database lab. Only UUID databases/roles created here are changed."""

import re
import sys
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/scripts"))
from sites import SQL_DIR, Sites, common_schema, fixture_sql  # noqa: E402


class Lab(Sites):
    def __init__(self, dsn, max_version=None):
        self.base_dsn = dsn
        self.max_version = max_version
        self.token = uuid.uuid4().hex[:12]
        self.names = {site: f"fragment_test_{self.token}_{site.lower()}" for site in "AB"}
        self.roles = {r: f"fragment_{self.token}_{r}" for r in ("global_reader", "b_reader", "site_writer")}
        self.selected = "AB"

    def rewrite(self, text):
        for old, new in self.roles.items():
            text = re.sub(r"\b" + old + r"\b", new, text)
        return text

    def dsn(self, site, role=None):
        return make_dsn(self.base_dsn, dbname=self.names[site], **({"user": self.roles[role]} if role else {}))

    def sql(self, site, statement, **kwargs):
        with closing(psycopg2.connect(self.dsn(site))) as connection, connection, connection.cursor() as cursor:
            cursor.execute(self.rewrite(statement))
        return SimpleNamespace(stdout="")

    def query(self, site, statement, **kwargs):
        with (
            closing(psycopg2.connect(self.dsn(site))) as connection,
            connection.cursor(cursor_factory=RealDictCursor) as c,
        ):
            c.execute(self.rewrite(statement))
            return [dict(row) for row in c.fetchall()]

    def initialize(self):
        with closing(psycopg2.connect(self.base_dsn)) as admin:
            admin.autocommit = True
            with admin.cursor() as cursor:
                for role in self.roles.values():
                    cursor.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
                for name in self.names.values():
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        source, manifest = common_schema(self.max_version)
        for site in "AB":
            permissions = (
                (SQL_DIR / "03_permissions.sql").read_text().replace(':"target_db"', '"' + self.names[site] + '"')
            )
            self.sql(
                site,
                source
                + f"\nINSERT INTO site_config VALUES(true,'{site}',{1 if site == 'A' else 0});\n"
                + f"INSERT INTO distributed_installation VALUES(true,1,'{manifest['source_sha256']}',1);\n"
                + fixture_sql(site)
                + "\n"
                + permissions,
            )
        self.upgrade()
        options = parse_dsn(self.base_dsn)
        # In this isolated lab both databases share a server; production sites do not.
        with closing(psycopg2.connect(self.dsn("A"))) as connection, connection, connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION postgres_fdw; CREATE SCHEMA site_b;")
            cursor.execute(
                sql.SQL(
                    "CREATE SERVER server_b FOREIGN DATA WRAPPER postgres_fdw OPTIONS(host {}, port {}, dbname {})"
                ).format(
                    sql.Literal(options.get("host", "127.0.0.1")),
                    sql.Literal(options.get("port", "5432")),
                    sql.Literal(self.names["B"]),
                )
            )
            # The test cluster uses trust auth. No stored production credentials.
            cursor.execute(
                sql.SQL("CREATE USER MAPPING FOR CURRENT_USER SERVER server_b OPTIONS(user {})").format(
                    sql.Literal(self.roles["b_reader"])
                )
            )
            cursor.execute(
                "IMPORT FOREIGN SCHEMA public LIMIT TO "
                "(product,product_image,category,seller_site,site_identity) FROM SERVER server_b INTO site_b"
            )
            cursor.execute(self.rewrite((SQL_DIR / "05_global_views.sql").read_text()))
            cursor.execute(self.rewrite((SQL_DIR / "06_routed_views.sql").read_text()))

    def cleanup(self):
        with closing(psycopg2.connect(self.base_dsn)) as admin:
            admin.autocommit = True
            with admin.cursor() as cursor:
                for name in self.names.values():
                    cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
                for role in self.roles.values():
                    cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


@contextmanager
def disposable_lab(dsn):
    lab = Lab(dsn)
    try:
        lab.initialize()
        yield lab
    finally:
        lab.cleanup()
