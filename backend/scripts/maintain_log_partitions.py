"""Create monthly log partitions, moving matching overflow rows atomically. No retention deletes."""

import argparse
import json
from datetime import datetime

from psycopg2 import sql

from scripts.migrate import LOCK_ID, connect


def ensure_month(month: datetime) -> dict:
    start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    name = "system_log_" + start.strftime("%Y%m")
    connection = connect()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='15s'")
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            cursor.execute("SELECT to_regclass(%s)", (name,))
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    "SELECT 1 FROM pg_inherits WHERE inhrelid=%s::regclass AND inhparent='system_log'::regclass",
                    (name,),
                )
                if cursor.fetchone() is None:
                    raise RuntimeError("Partition name occupied by a different relation")
                return {"partition": name, "created": False, "moved": 0}
            cursor.execute("LOCK TABLE system_log IN ACCESS EXCLUSIVE MODE")
            cursor.execute(sql.SQL("CREATE TABLE {} (LIKE system_log INCLUDING ALL)").format(sql.Identifier(name)))
            cursor.execute(
                sql.SQL("""WITH moved AS (
                DELETE FROM system_log_default WHERE created_at >= %s AND created_at < %s RETURNING *)
                INSERT INTO {} SELECT * FROM moved""").format(sql.Identifier(name)),
                (start, end),
            )
            moved = cursor.rowcount
            cursor.execute(
                sql.SQL("ALTER TABLE system_log ATTACH PARTITION {} FOR VALUES FROM ({}) TO ({})").format(
                    sql.Identifier(name), sql.Literal(start), sql.Literal(end)
                )
            )
        return {"partition": name, "created": True, "moved": moved}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", type=lambda value: datetime.strptime(value, "%Y-%m"), required=True)
    args = parser.parse_args()
    print(json.dumps(ensure_month(args.month)))


if __name__ == "__main__":
    main()
