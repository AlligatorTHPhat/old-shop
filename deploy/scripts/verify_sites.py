"""Real PostgreSQL integration checks, including outages and TCP authentication.

Only touches the isolated sites selected by sites.py. Every committed test change
is removed in finally blocks; transactions used for other writes are rolled back.
"""

import hashlib
import json
import os
import secrets
import statistics
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sites import EVIDENCE, SQL_DIR, Sites, common_schema, fixture, prepare, save_json

QUERY_VALUES = {"from_date": "2026-11-01", "to_date": "2026-12-01", "product_id": 4}
PRODUCT_KEYS = tuple(fixture("A")["products"][0])
IMAGE_KEYS = tuple(fixture("A")["images"][0])


def schema_contract(sites, site):
    return sites.query(
        site,
        """SELECT json_build_object(
        'columns', (SELECT json_agg(r) FROM (
            SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull,
                pg_get_expr(d.adbin,d.adrelid) AS default_value
            FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p')
            ORDER BY c.relname,a.attnum) r),
        'constraints', (SELECT json_agg(r) FROM (
            SELECT c.relname,k.contype,pg_get_constraintdef(k.oid) AS definition
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            WHERE c.relnamespace='public'::regnamespace ORDER BY 1,2,3) r),
        'indexes', (SELECT json_agg(r) FROM (
            SELECT indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY indexdef) r),
        'triggers', (SELECT json_agg(r) FROM (
            SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) AS definition FROM pg_trigger t
            JOIN pg_class c ON c.oid=t.tgrelid WHERE NOT t.tgisinternal
                AND c.relnamespace='public'::regnamespace ORDER BY 1,2) r),
        'functions', (SELECT json_agg(r) FROM (
            SELECT p.oid::regprocedure::text AS signature, pg_get_functiondef(p.oid) AS definition
            FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.prokind='f'
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
                    AND d.objid=p.oid AND d.deptype='e') ORDER BY 1) r),
        'common_views', (SELECT json_agg(r) FROM (
            SELECT viewname,definition FROM pg_views WHERE schemaname='public'
                AND viewname NOT LIKE 'v_%' ORDER BY viewname) r)
    ) AS contract""",
    )[0]["contract"]


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def denied(sites, site, statement, *, state="42501", role="reader", **kwargs):
    result = sites.sql(site, "BEGIN;\n" + statement + ";\nROLLBACK;", role=role, check=False, **kwargs)
    check(result.returncode != 0 and state in result.stderr, f"Expected SQLSTATE {state}; got {result.stderr[-1000:]}")
    return {"expected_sqlstate": state, "error": result.stderr.strip()[-1000:]}


def writer_insert(site, product_id=None):
    seller = 101 if site == "A" else 202
    columns = "seller_id,category_id,title,price,quantity"
    values = f"{seller},1,'Verification product',123,2"
    if product_id is not None:
        columns += ",product_id"
        values += f",{product_id}"
    return f"INSERT INTO product({columns}) VALUES({values}) RETURNING product_id"


def remote_args(sites):
    return {
        "connect_host": sites.env["SITE_B_FDW_HOST"],
        "connect_port": sites.env["SITE_B_FDW_PORT"],
        "database": sites.env["SITE_B_DB_NAME"],
        "password_site": "B",
        "role": "reader",
    }


def expected_queries():
    """Independent fixture oracle. No database query used to compute expected results."""
    products = fixture("A")["products"] + fixture("B")["products"]
    images = fixture("A")["images"] + fixture("B")["images"]
    categories = {1: "Electronics", 2: "Books", 3: "Empty category"}
    products.sort(key=lambda p: p["product_id"])
    visible = [p for p in products if not p["is_deleted"]]
    selected = [p for p in visible if QUERY_VALUES["from_date"] <= p["created_at"] < QUERY_VALUES["to_date"]]
    target = next(p for p in products if p["product_id"] == QUERY_VALUES["product_id"])
    target_images = sorted([i for i in images if i["product_id"] == target["product_id"]], key=lambda i: i["image_id"])
    return {
        "Q1": [{k: p[k] for k in ("product_id", "title", "site_id")} for p in products if p["site_id"] == "B"],
        "Q2": [
            {
                "product_id": p["product_id"],
                "title": p["title"],
                "category_name": categories[p["category_id"]],
                "site_id": p["site_id"],
            }
            for p in visible
        ],
        "Q3": [
            {
                "product_id": target["product_id"],
                "title": target["title"],
                "site_id": "B",
                "image_id": i["image_id"],
                "image_url": i["image_url"],
            }
            for i in target_images
        ],
        "Q4": [
            {"category_id": cid, "name": name, "product_count": sum(p["category_id"] == cid for p in visible)}
            for cid, name in categories.items()
        ],
        "Q5": [
            {
                "category_id": cid,
                "name": name,
                "product_count": len(rows),
                "average_price": statistics.mean(p["price"] for p in rows) if rows else None,
            }
            for cid, name in categories.items()
            for rows in [[p for p in selected if p["category_id"] == cid]]
        ],
        "Q6": [
            {"seller_id": sid, "site_id": site}
            for sid, site in [(101, "A"), (103, "A"), (105, "A"), (202, "B"), (204, "B"), (206, "B")]
            if not any(p["seller_id"] == sid for p in selected)
        ],
    }


def verify(sites):
    if sites.selected != "AB":
        raise ValueError("Automatic outage checks require both local sites; use the multi-host runbook remotely")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "M1, one host / two virtual IPs",
        "physical_hosts_verified": False,
        "checks": {},
        "queries": {},
    }
    original_containers = sites.run(["ps", "--format", "json"]).stdout

    def run(code, function):
        started = time.perf_counter()
        try:
            detail = function()
        except Exception as exc:
            report["checks"][code] = {"status": "FAIL", "error": sites.redact(str(exc))}
            save_json(EVIDENCE / "test_results.json", report)
            raise
        report["checks"][code] = {
            "status": "PASS",
            "seconds": round(time.perf_counter() - started, 3),
            "detail": detail,
        }
        save_json(EVIDENCE / "test_results.json", report)
        print(f"{code}: PASS", flush=True)

    def connection():
        data = sites.query(
            "A",
            """SELECT current_database() AS database, current_user AS role,
            inet_client_addr()::text AS client_address,inet_server_addr()::text AS server_address,
            (SELECT site_id FROM site_identity) AS site_id,
            (SELECT title FROM product WHERE product_id=2) AS remote_title""",
            **remote_args(sites),
        )[0]
        check(
            data["database"] == sites.env["SITE_B_DB_NAME"]
            and data["role"] == "b_reader"
            and data["site_id"] == "B"
            and data["remote_title"] is not None,
            "Wrong remote site",
        )
        check(data["client_address"] != data["server_address"], "Connection did not cross virtual hosts")
        return data

    def visibility():
        try:
            sites.sql("B", writer_insert("B", 100002) + ";", role="writer")
            remote = sites.query("A", "SELECT product_id,title FROM v_product WHERE product_id=100002", role="global")
            check(len(remote) == 1, "B's committed insert is missing from a new A transaction")
            # Persistent session: same FDW snapshot until the A transaction ends.
            process = subprocess.Popen(
                sites.compose
                + [
                    "exec",
                    "-T",
                    "pg-a",
                    "psql",
                    "-X",
                    "-qAt",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "site_admin",
                    "-d",
                    sites.env["SITE_A_DB_NAME"],
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, **sites.env},
            )
            try:
                process.stdin.write("BEGIN; SELECT price FROM site_b.product WHERE product_id=100002;\n")
                process.stdin.flush()
                before = process.stdout.readline().strip()
                check(before == "123.00", f"Unexpected initial snapshot: {before}")
                sites.sql("B", "UPDATE product SET price=456 WHERE product_id=100002;", role="writer")
                process.stdin.write(
                    "SELECT price FROM site_b.product WHERE product_id=100002; COMMIT;\n"
                    "SELECT price FROM site_b.product WHERE product_id=100002;\n\\q\n"
                )
                process.stdin.flush()
                out, err = process.communicate(timeout=20)
                check(
                    process.returncode == 0 and out.splitlines() == ["123.00", "456.00"],
                    f"FDW snapshot/new transaction mismatch: {out} {err}",
                )
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            return {"insert_visible": remote, "same_transaction_price": "123.00", "new_transaction_price": "456.00"}
        finally:
            sites.sql("B", "DELETE FROM product WHERE product_id=100002;", role="writer")

    def privileges():
        result = {}
        for site in "AB":
            check(
                sites.query(site, "SELECT count(*) AS n FROM product", role="reader")[0]["n"] == 5,
                "Reader SELECT failed",
            )
            for name, sql in {
                "update": "UPDATE product SET price=0 WHERE false",
                "insert": writer_insert(site),
                "delete": "DELETE FROM product WHERE false",
                "secret": "SELECT password_hash FROM user_secret",
                "wallet": "SELECT balance FROM user_wallet",
                "full_users": "SELECT * FROM users_full",
                "site_change": "UPDATE site_config SET site_id=site_id",
                "function_bypass": (
                    "SELECT create_user_with_hash('attack','attack@example.invalid','password','attack')"
                ),
            }.items():
                result[f"{site}_{name}"] = denied(sites, site, sql)
            result[f"{site}_writer_identity"] = denied(
                sites, site, "UPDATE site_config SET site_id=site_id", role="writer"
            )
            result[f"{site}_writer_mapping"] = denied(
                sites, site, "UPDATE seller_site SET site_id=site_id", role="writer"
            )
        for name, sql in {
            "update": "UPDATE product SET price=0 WHERE false",
            "delete": "DELETE FROM product WHERE false",
        }.items():
            result[f"A_to_B_{name}"] = denied(sites, "A", sql, **remote_args(sites))
        result["foreign_update"] = denied(
            sites, "A", "UPDATE site_b.product SET price=price WHERE product_id=2", role="admin"
        )
        result["global_write"] = denied(
            sites, "A", "UPDATE v_product SET price=0 WHERE false", state="55000", role="global"
        )
        result["global_table_write"] = denied(sites, "A", "UPDATE product SET price=0 WHERE false", role="global")
        wrong_source = sites.sql(
            "B",
            "SELECT 1;",
            role="reader",
            connect_host=sites.env["SITE_A_VIRTUAL_IP"],
            database=sites.env["SITE_A_DB_NAME"],
            password_site="A",
            check=False,
        )
        check(
            wrong_source.returncode != 0 and "pg_hba.conf rejects connection" in wrong_source.stderr,
            "HBA accepted an unapproved reader source",
        )
        result["unapproved_source"] = {"rejected": True, "error": wrong_source.stderr.strip()}
        return result

    def outage_b():
        try:
            sites.run(["stop", "-t", "2", "pg-b"])
            check(sites.query("A", "SELECT count(*) AS n FROM product")[0]["n"] == 5, "Local A read failed")
            sites.sql("A", "BEGIN;" + writer_insert("A") + ";ROLLBACK;", role="writer")
            start = time.perf_counter()
            failed = sites.sql("A", "SELECT count(*) FROM v_product;", check=False, role="global")
            elapsed = time.perf_counter() - start
            check(
                failed.returncode != 0
                and any(code in failed.stderr for code in ("08001", "08006", "57014"))
                and elapsed < 13,
                f"Remote query did not fail within timeout: {elapsed}s {failed.stderr}",
            )
            return {"local_read_write": "PASS", "remote_error": failed.stderr.strip(), "failure_seconds": elapsed}
        finally:
            sites.run(["up", "-d", "--wait", "--wait-timeout", "60", "pg-b"])
            check(
                len(sites.query("A", "SELECT product_id FROM site_b.product WHERE product_id=2")) == 1,
                "B did not recover",
            )

    def integrity():
        result = {}
        for site, first, seller in (("A", 1, 101), ("B", 2, 202)):
            foreign = "B" if site == "A" else "A"
            for name, statement, state in (
                ("duplicate_pk", writer_insert(site, first), "23505"),
                ("missing_category", f"UPDATE product SET category_id=999999 WHERE product_id={first}", "23503"),
                ("negative_price", f"UPDATE product SET price=-1 WHERE product_id={first}", "23514"),
                ("negative_stock", f"UPDATE product SET quantity=-1 WHERE product_id={first}", "23514"),
                ("wrong_site", f"UPDATE product SET site_id='{foreign}' WHERE product_id={first}", "23514"),
                ("wrong_id", writer_insert(site, 100001 if site == "B" else 100002), "23514"),
                ("seller_fk", writer_insert(site).replace(f"VALUES({seller},", "VALUES(999999,"), "23503"),
                (
                    "seller_site_fk",
                    writer_insert(site).replace(f"VALUES({seller},", f"VALUES({202 if site == 'A' else 101},"),
                    "23503",
                ),
                (
                    "missing_product",
                    "INSERT INTO product_image(product_id,image_url) VALUES(999999,'/missing')",
                    "23503",
                ),
                (
                    "remote_parent",
                    f"INSERT INTO product_image(product_id,image_url) VALUES("
                    f"{2 if site == 'A' else 1},'/remote-parent')",
                    "23503",
                ),
                (
                    "wrong_image_id",
                    "INSERT INTO product_image(image_id,product_id,image_url) VALUES("
                    f"{100002 if site == 'A' else 100001},{first},'/wrong')",
                    "23514",
                ),
                (
                    "ownership_change",
                    f"UPDATE product SET seller_id={103 if site == 'A' else 204} WHERE product_id={first}",
                    "23514",
                ),
            ):
                result[f"{site}_{name}"] = denied(sites, site, statement, state=state, role="writer")
        return result

    def reconstruction():
        detail = {}
        for table, view, field, key in (
            ("product", "v_product", "products", "product_id"),
            ("product_image", "v_product_image", "images", "image_id"),
        ):
            local = {site: sites.query(site, f"SELECT * FROM {table} ORDER BY {key}") for site in "AB"}
            actual = sites.query("A", f"SELECT * FROM {view} ORDER BY {key}", role="global")
            combined = sorted(local["A"] + local["B"], key=lambda r: r[key])
            check(actual == combined, f"Full-row reconstruction mismatch: {table}")
            check(not ({r[key] for r in local["A"]} & {r[key] for r in local["B"]}), f"Overlapping keys: {table}")
            keys = PRODUCT_KEYS if field == "products" else IMAGE_KEYS
            expected = sorted(fixture("A")[field] + fixture("B")[field], key=lambda r: r[key])
            check(
                [{k: r[k] for k in keys} for r in actual] == expected, f"Fixture completeness/content mismatch: {table}"
            )
            detail[table] = {
                "A": len(local["A"]),
                "B": len(local["B"]),
                "global": len(actual),
                "full_row_sha256": hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest(),
            }
        contracts = {site: schema_contract(sites, site) for site in "AB"}
        check(contracts["A"] == contracts["B"], "Site schema drift")
        save_json(EVIDENCE / "schema_comparison.json", {"equal": True, "common_contract": contracts["A"]})
        return detail

    def references():
        result = {}
        for table in ("category", "seller_site"):
            a = sites.query("A", f"SELECT * FROM {table} ORDER BY 1")
            b = sites.query("B", f"SELECT * FROM {table} ORDER BY 1")
            check(a == b, f"Reference copies differ: {table}")
            view = "v_category" if table == "category" else "v_seller_site"
            check(sites.query("A", f"SELECT * FROM {view} ORDER BY 1", role="global") == a, "Reference duplication")
            result[table] = len(a)
        return result

    def queries():
        expected = expected_queries()
        save_json(SQL_DIR / "expected_results.json", {"parameters": QUERY_VALUES, "queries": expected})
        for key, wanted in expected.items():
            sql = (SQL_DIR / "queries" / f"{key}.sql").read_text()
            role = "admin" if key == "Q1" else "global"
            actual = sites.query("A", sql, values=QUERY_VALUES, role=role)
            check(actual == wanted, f"{key} result mismatch: {actual} != {wanted}")
            report["queries"][key] = {"sql": sql, "parameters": QUERY_VALUES, "expected": wanted, "actual": actual}
        empty = sites.query("A", (SQL_DIR / "queries/Q3.sql").read_text(), values={"product_id": 2}, role="global")
        check(len(empty) == 1 and empty[0]["image_id"] is None, "Product without images was lost")
        return {"queries": list(expected), "detail_without_images": "PASS"}

    def concurrent_ids():
        def batch(site):
            seller = 101 if site == "A" else 202
            sql = (
                "BEGIN; WITH inserted AS (INSERT INTO product(seller_id,category_id,title,price,quantity) "
                f"SELECT {seller},1,'Concurrent',1,1 FROM generate_series(1,10) RETURNING product_id) "
                "SELECT json_agg(product_id) FROM inserted; ROLLBACK;"
            )
            result = sites.sql(site, sql, role="writer")
            return site, json.loads(result.stdout)

        with ThreadPoolExecutor(max_workers=4) as pool:
            batches = list(pool.map(batch, ["A", "B", "A", "B"]))
        ids = [identifier for _, batch_ids in batches for identifier in batch_ids]
        check(len(ids) == len(set(ids)) == 40, "Concurrent ID collision")
        check(
            all(all(i % 2 == (1 if site == "A" else 0) for i in batch_ids) for site, batch_ids in batches),
            "Sequence allocation does not match owner",
        )
        return {"concurrent_writers": 4, "allocated_unique_ids": len(ids), "writes_rolled_back": True}

    def outage_a():
        try:
            sites.run(["stop", "-t", "2", "pg-a"])
            check(sites.query("B", "SELECT count(*) AS n FROM product")[0]["n"] == 5, "Local B read failed")
            sites.sql("B", "BEGIN;" + writer_insert("B") + ";ROLLBACK;", role="writer")
            return {"B_local_read_write_with_A_down": True}
        finally:
            sites.run(["up", "-d", "--wait", "--wait-timeout", "60", "pg-a"])
            check(sites.query("A", "SELECT site_id FROM site_b.site_identity") == [{"site_id": "B"}], "Recovery failed")

    def restart():
        before = sites.inventory()
        sites.bootstrap()  # Rerun must preserve content and not reload fixtures.
        sites.configure_fdw()
        after = sites.inventory()
        check(before == after, "Bootstrap rerun changed site identity/data/version")
        # A second, disposable Compose project proves the setup does not rely on
        # leftover data in either persistent site. Only this project's volumes are deleted.
        with tempfile.TemporaryDirectory(prefix="oldshop-sites-rebuild-") as directory:
            env_file = Path(directory) / ".env"
            prepare(env_file)
            values = dict(sites.env)
            values.update({key: secrets.token_hex(24) for key in values if key.endswith("_PASSWORD")})
            values.update(
                SITE_A_PORT="0",
                SITE_B_PORT="0",
                SITES_SUBNET="172.29.83.0/24",
                SITE_A_VIRTUAL_IP="172.29.83.11",
                SITE_B_VIRTUAL_IP="172.29.83.12",
                SITE_B_FDW_HOST="172.29.83.12",
                SITE_B_FDW_PORT="5432",
                SITE_B_READER_SOURCE_CIDR="172.29.83.11/32",
                CATALOGUE_VIRTUAL_IP="172.29.83.20",
            )
            env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
            fresh = Sites(env_file, project="oldshop-sites-rebuild-" + secrets.token_hex(4))
            try:
                fresh.run(["up", "-d", "--wait", "--wait-timeout", "90"])
                fresh.bootstrap()
                fresh.configure_fdw()
                check(schema_contract(sites, "B") == schema_contract(fresh, "B"), "Clean rebuild schema differs")
                for code, expected in expected_queries().items():
                    actual = fresh.query(
                        "A",
                        (SQL_DIR / "queries" / f"{code}.sql").read_text(),
                        values=QUERY_VALUES,
                        role="admin" if code == "Q1" else "global",
                    )
                    check(actual == expected, f"Fresh installation {code} failed")
                for site in "AB":
                    check(
                        fresh.query(site, "SELECT count(*) AS n FROM product_image")[0]["n"] == 8,
                        "Clean image fixture mismatch",
                    )
                detail = {
                    "bootstrap_idempotent": True,
                    "clean_rebuild_verified": True,
                    "fresh_queries": list(expected_queries()),
                    "fresh_inventory": fresh.inventory(),
                }
                save_json(EVIDENCE / "clean_rebuild.json", detail)
                return detail
            finally:
                fresh.run(["down", "--volumes"], check=False)

    def performance():
        results = {}
        for name, sql in {
            "local": "SELECT count(*) FROM product",
            "remote": "SELECT count(*) FROM site_b.product",
            "global": "SELECT count(*) FROM v_product",
        }.items():
            timings = []
            for _ in range(7):
                # EXPLAIN is a statement rather than a SELECT subquery.
                result = sites.sql("A", "EXPLAIN (ANALYZE, VERBOSE, FORMAT JSON) " + sql + ";")
                plan = json.loads(result.stdout)[0]
                timings.append(plan["Execution Time"])
            results[name] = {
                "samples_ms": timings,
                "median_ms": statistics.median(timings),
                "p95_ms": sorted(timings)[-1],
                "plan": plan,
            }
        results["limitations"] = (
            "Seed-scale, one Docker host; p95 uses nearest rank (7 samples), not a capacity benchmark."
        )
        save_json(EVIDENCE / "performance_results.json", results)
        return results

    run("T01", connection)
    run("T02", visibility)
    run("T03", privileges)
    run("T04", outage_b)
    run("T05", integrity)
    run("T06", reconstruction)
    run("T07", references)
    run("T08", queries)
    run("T09", concurrent_ids)
    run("T10", outage_a)
    run("T11", restart)
    run("T12", performance)
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["status"] = "PASS"
    report["clean_rebuild_verified"] = report["checks"]["T11"]["detail"]["clean_rebuild_verified"]
    report["inventory"] = sites.inventory()
    report["compose_before"] = original_containers
    report["source_sha256"] = common_schema()[1]["source_sha256"]
    save_json(EVIDENCE / "test_results.json", report)
    print(f"All virtual-site checks passed. Evidence: {EVIDENCE / 'test_results.json'}")
