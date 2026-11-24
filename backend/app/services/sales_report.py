"""Primary-only analytics reads. Gross item sales never replace the legacy net-revenue field."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text


def read(db, year: int | None = None) -> dict:
    year = year or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).year
    from app.core.config import settings

    if settings.BUCKET_MODE:
        # Order snapshots and subtotals are core-owned. A local product JOIN
        # would silently empty this report after catalogue leaves core.
        daily = (
            db.execute(
                text("""
                SELECT (o.order_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS day,
                   sum(d.subtotal) AS gross_sales_vnd,sum(d.quantity) AS item_quantity
            FROM "order" o JOIN order_detail d USING(order_id)
            WHERE o.order_status=3 AND NOT o.is_deleted
                  AND (o.order_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Ho_Chi_Minh')::date>=make_date(:year,1,1)
                  AND (o.order_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Ho_Chi_Minh')::date<make_date(:year+1,1,1)
            GROUP BY 1 ORDER BY 1
        """),
                {"year": year},
            )
            .mappings()
            .all()
        )
        return dict(
            year=year,
            as_of=datetime.now(UTC),
            available=True,
            stale=False,
            gross_sales_vnd=sum(int(row["gross_sales_vnd"]) for row in daily),
            daily=[dict(row) for row in daily],
        )
    as_of = db.execute(
        text("""SELECT ended_at FROM etl_runs
        WHERE status='success' AND details ? 'aggregate' ORDER BY ended_at DESC LIMIT 1""")
    ).scalar()
    rows = (
        db.execute(
            text("""SELECT report_date AS day,sum(gross_sales_vnd) AS gross_sales_vnd,
        sum(item_quantity) AS item_quantity FROM report_daily_sales
        WHERE report_date>=make_date(:year,1,1) AND report_date<make_date(:year+1,1,1)
        GROUP BY report_date ORDER BY report_date"""),
            {"year": year},
        )
        .mappings()
        .all()
    )
    return {
        "year": year,
        "as_of": as_of,
        "available": as_of is not None,
        "stale": as_of is None or (datetime.now(UTC) - as_of).total_seconds() > 300,
        "gross_sales_vnd": sum(int(row["gross_sales_vnd"]) for row in rows),
        "daily": [dict(row) for row in rows],
    }
