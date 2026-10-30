"""Rebuild gross item sales by VN business day and CURRENT seller/category, on PG."""

from datetime import UTC, datetime

from etl.transform import QualityError, vnd


def rebuild(source, writer, run_id):
    rows = source.rows("""SELECT
        (o.order_date AT TIME ZONE t.source_zone AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS day,
        p.seller_id,p.category_id,count(DISTINCT o.order_id) AS orders_count,
        sum(d.quantity) AS item_quantity,sum(d.subtotal) AS gross
        FROM "order" o JOIN order_detail d USING(order_id) JOIN product p USING(product_id)
        LEFT JOIN etl_time_origin t ON t.source_table='order'
         AND t.source_key=jsonb_build_object('order_id',o.order_id) AND t.field_name='order_date'
         AND t.source_value=o.order_date
        WHERE o.order_status=3 AND NOT o.is_deleted
        GROUP BY day,p.seller_id,p.category_id""")
    values = []
    for row in rows:
        if row["day"] is None:
            raise QualityError("aggregate_missing_timestamp_origin")
        values.append(
            (
                row["day"],
                row["seller_id"],
                row["category_id"],
                row["orders_count"],
                row["item_quantity"],
                vnd(row["gross"]),
                datetime.now(UTC),
                str(run_id),
            )
        )
    with writer, writer.cursor() as cursor:
        cursor.execute("DELETE FROM report_daily_sales")
        if values:
            cursor.executemany("INSERT INTO report_daily_sales VALUES(%s,%s,%s,%s,%s,%s,%s,%s)", values)
    return {
        "groups": len(values),
        "gross_sales_vnd": sum(row[5] for row in values),
        "business_timezone": "Asia/Ho_Chi_Minh",
    }
