"""Historical read-only checks for migration 007; use verify_indexes for JSON releases."""

import argparse
import hashlib
import json
import re
from contextlib import closing

from app.services.mongo import get_database
from scripts.migrate import DATABASE_DIR, connect

SPECS = {
    "idx_product_visible_date_id": (
        "product",
        ["created_at DESC", "product_id"],
        "status=1 AND is_deleted=false",
    ),
    "idx_product_image_url": ("product_image", ["image_url"], None),
    "idx_user_profile_avatar_url": ("user_profile", ["avatar_url"], None),
    "idx_order_voucher_lookup": ("order", ["voucher_id"], None),
    "idx_etl_runs_started": ("etl_runs", ["started_at DESC"], None),
    "idx_etl_runs_aggregate_success": (
        "etl_runs",
        ["ended_at DESC"],
        "status='success'::text AND details?'aggregate'::text",
    ),
    "idx_etl_outbox_entity_pending": (
        "etl_outbox",
        ["entity_type", "entity_key", "event_id"],
        "status<>'done'::text",
    ),
    "idx_etl_outbox_pending_event": (
        "etl_outbox",
        ["event_id", "available_at"],
        "status=ANYARRAY['pending'::text,'dead'::text]",
    ),
    "idx_user_role_role_user": ("user_role", ["role_id", "user_id"], None),
}


def normalize(value):
    return re.sub(r"[\s()]", "", value or "").lower()


def physical_index_bytes(connection, name):
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH RECURSIVE tree(oid) AS (SELECT %s::regclass::oid UNION ALL
            SELECT i.inhrelid FROM pg_inherits i JOIN tree t ON i.inhparent=t.oid)
            SELECT sum(pg_relation_size(oid)) FROM tree""",
            (name,),
        )
        return int(cursor.fetchone()[0])


def verify(preflight=False, mongo=False):
    with closing(connect()) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT version,checksum FROM schema_migrations ORDER BY version"
            )
            history = cursor.fetchall()
            local = {
                p.name[:3]: p
                for p in (DATABASE_DIR / "04_migrations").glob("[0-9][0-9][0-9]_*.sql")
            }
            applied = [r[0] for r in history]
            assert applied == sorted(local)[: len(applied)] and len(applied) >= 6, (
                "Expected a recognized post-006 schema"
            )
            for version, checksum in history:
                assert (
                    hashlib.sha256(local[version].read_bytes()).hexdigest() == checksum
                ), "Migration checksum mismatch"
            result = {"versions": applied, "indexes": {}}
            if not preflight:
                assert "007" in applied, "Migration 007 is not installed"
                for name, (table, keys, predicate) in SPECS.items():
                    cursor.execute(
                        """SELECT t.relname,am.amname,i.indisunique,i.indisvalid,
                        ARRAY(SELECT pg_get_indexdef(i.indexrelid,k,true) ||
                        CASE WHEN (i.indoption[k-1] & 1)=1 THEN ' DESC' ELSE '' END
                        FROM generate_series(1,i.indnkeyatts) k),
                        pg_get_expr(i.indpred,i.indrelid),i.indoption::smallint[],i.indnatts=i.indnkeyatts
                        FROM pg_index i JOIN pg_class ix ON ix.oid=i.indexrelid
                        JOIN pg_class t ON t.oid=i.indrelid JOIN pg_am am ON am.oid=ix.relam
                        WHERE ix.oid=to_regclass(%s)""",
                        (name,),
                    )
                    row = cursor.fetchone()
                    assert row and row[:4] == (table, "btree", False, True), name
                    assert [normalize(k) for k in row[4]] == [
                        normalize(k) for k in keys
                    ], name
                    assert normalize(row[5]) == normalize(predicate), (name, row[5])
                    assert row[6] == [
                        3 if key.endswith(" DESC") else 0 for key in keys
                    ], name
                    assert row[7], f"Unexpected INCLUDE columns: {name}"
                    cursor.execute(
                        """WITH RECURSIVE tree(oid) AS (SELECT %s::regclass::oid UNION ALL
                        SELECT i.inhrelid FROM pg_inherits i JOIN tree t ON i.inhparent=t.oid)
                        SELECT count(*),bool_and(i.indisvalid) FROM tree JOIN pg_index i ON i.indexrelid=tree.oid""",
                        (name,),
                    )
                    count, valid = cursor.fetchone()
                    assert valid and count == (5 if table == "order" else 1), name
                    result["indexes"][name] = {
                        "physical_bytes": physical_index_bytes(connection, name),
                        "relations": count,
                    }
    if mongo:
        info = (
            get_database()
            .product_details.index_information()
            .get("idx_live_product_image_key")
        )
        assert (
            info
            and info["key"] == [("images.key", 1)]
            and not info.get("unique", False)
        ), "Missing shared-image Mongo index"
        assert info.get("partialFilterExpression") == {"deleted": False}, (
            "Wrong Mongo live-image predicate"
        )
        result["mongo_live_image_index"] = True
    return {"result": "PASS", **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--mongo", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.preflight, args.mongo)))


if __name__ == "__main__":
    main()
