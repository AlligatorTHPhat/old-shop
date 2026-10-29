"""Hash the exact v0 columns of all source rows, without exporting PII to evidence."""

import argparse
import json
from pathlib import Path

from psycopg2 import sql

from scripts.migrate import DATABASE_DIR, connect


def snapshot() -> dict:
    contract = json.loads((DATABASE_DIR / "baseline_v0.json").read_text())
    columns = {}
    for table, column, *_ in contract["columns"]:
        columns.setdefault(table, []).append(column)
    result = {}
    connection = connect()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT to_regclass('user_core') IS NOT NULL")
            split = cursor.fetchone()[0]
            for table, fields in columns.items():
                relation = "users_full" if table == "user" and split else table
                query = sql.SQL("""SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,E'\\n'
                     ORDER BY row_to_json(t)::text),'')) FROM (SELECT {} FROM {}) t""").format(
                    sql.SQL(",").join(map(sql.Identifier, fields)), sql.Identifier(relation)
                )
                cursor.execute(query)
                count, digest = cursor.fetchone()
                result[table] = {"rows": count, "digest": digest}
        return result
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    result = snapshot()
    if args.compare:
        previous = json.loads(args.compare.read_text())
        changed = [table for table in result if result[table] != previous.get(table)]
        if changed:
            raise RuntimeError("Row reconciliation failed for: " + ", ".join(changed))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"result": "PASS", "tables": len(result), "rows": {name: data["rows"] for name, data in result.items()}}
        )
    )


if __name__ == "__main__":
    main()
