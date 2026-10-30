"""Retry unlinked files after Mongo projection catch-up. No bucket scans or orphan sweeps."""

from psycopg2.extras import RealDictCursor

from app.services.storage import delete_media


def run(connection, database):
    result = {"deleted": 0, "deferred": 0, "errors": 0}
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            "SELECT * FROM media_deletions WHERE status='pending' AND "
            "available_at<=clock_timestamp() ORDER BY deletion_id LIMIT 100"
        )
        rows = list(cursor.fetchall())
    connection.commit()
    for row in rows:
        path = row["url_path"].removeprefix("/media/")
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT EXISTS(SELECT 1 FROM product_image WHERE image_url=%s)
                    OR EXISTS(SELECT 1 FROM user_profile WHERE avatar_url=%s)
                    OR EXISTS(SELECT 1 FROM etl_outbox WHERE status<>'done')""",
                    (row["url_path"], row["url_path"]),
                )
                referenced = cursor.fetchone()[0]
            connection.commit()
            if referenced or database.product_details.find_one(
                {"deleted": False, "images.key": path}, {"_id": 1}, max_time_ms=2000
            ):
                result["deferred"] += 1
                continue
            delete_media(row["url_path"])
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE media_deletions SET status='done',processed_at=clock_timestamp(),"
                    "last_error_code=NULL WHERE deletion_id=%s",
                    (row["deletion_id"],),
                )
            result["deleted"] += 1
        except Exception:
            connection.rollback()
            with connection, connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE media_deletions SET attempts=attempts+1,"
                    "last_error_code='media_cleanup_unavailable',"
                    "available_at=clock_timestamp()+interval '60 seconds' WHERE deletion_id=%s",
                    (row["deletion_id"],),
                )
            result["errors"] += 1
    return result
