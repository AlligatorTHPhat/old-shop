"""Read a consistent PG snapshot using explicit allowlists, never users_full/PII."""

from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

from scripts.migrate import connect

SOURCES = {
    "product": ("product", "product_id", "product_details"),
    "order": ("order", "order_id", "order_snapshots"),
    "review": ("review", "review_id", "reviews"),
    "system_log": ("system_log", "log_id", "system_logs"),
    "violation_log": ("violation_log", "log_id", "violation_logs"),
    "contact": ("system_feedback", "feedback_id", "contact_messages"),
}
FIELDS = {
    "product": (
        "product_id,category_id,description,video_url,weight_grams,dimensions,"
        "condition_rating,warranty_months,created_at,updated_at,is_deleted"
    ),
    "order": (
        "order_id,buyer_id,voucher_id,total_amount,shipping_fee,discount_amount,"
        "final_amount,order_status,order_date,is_deleted"
    ),
    "review": "review_id,product_id,buyer_id,rating,title,content,created_at,updated_at,is_deleted",
    "system_log": "log_id,user_id,action,resource_type,resource_id,created_at",
    "violation_log": "log_id,user_id,action_taken,created_at",
    "contact": "feedback_id,user_id,status,created_at",
}


class Source:
    def __init__(self):
        self.connection = connect()
        self.connection.set_session(isolation_level="REPEATABLE READ", readonly=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def rows(self, statement, params=()):
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(statement, params)
            return [dict(row) for row in cursor.fetchall()]

    def keys(self, entity):
        table, column, _ = SOURCES[entity]
        fields = sql.SQL("jsonb_build_object('id',{})").format(sql.Identifier(column))
        if entity == "system_log":
            fields = sql.SQL("jsonb_build_object('id',log_id,'created_at',created_at)")
        with self.connection.cursor(name="etl_keys_" + entity) as cursor:
            cursor.itersize = 500
            cursor.execute(
                sql.SQL("SELECT {} FROM {} ORDER BY {}").format(fields, sql.Identifier(table), sql.Identifier(column))
            )
            for row in cursor:
                yield row[0]

    def get(self, entity, key):
        table, column, _ = SOURCES[entity]
        source_key = sql.SQL("jsonb_build_object({}, {})").format(sql.Literal(column), sql.Identifier(column))
        clause = sql.SQL("{}=%s").format(sql.Identifier(column))
        params = [key["id"]]
        if entity == "system_log":
            source_key = sql.SQL("jsonb_build_object('log_id',log_id,'created_at',created_at)")
            clause += sql.SQL(" AND created_at=%s::timestamp")
            params.append(key["created_at"])
        query = sql.SQL("SELECT {}, {} AS _source_key FROM {} WHERE {}").format(
            sql.SQL(FIELDS[entity]), source_key, sql.Identifier(table), clause
        )
        rows = self.rows(query, params)
        return rows[0] if rows else None

    def origins(self, entity, source_key):
        table, _, _ = SOURCES[entity]
        return {
            row["field_name"]: (row["source_value"], row["source_zone"])
            for row in self.rows(
                "SELECT field_name,source_value,source_zone FROM etl_time_origin "
                "WHERE source_table=%s AND source_key=%s",
                (table, Json(source_key)),
            )
        }

    def images(self, product_id):
        return self.rows(
            """SELECT image_id,image_url,content_type,size_bytes,is_primary,display_order
            FROM product_image WHERE product_id=%s ORDER BY display_order,image_id""",
            (product_id,),
        )

    def items(self, order_id):
        return self.rows(
            """SELECT d.product_id,d.quantity,d.price_at_purchase,d.subtotal,p.title,
            p.category_id,p.seller_id FROM order_detail d JOIN product p USING(product_id)
            WHERE d.order_id=%s ORDER BY d.order_detail_id""",
            (order_id,),
        )

    def payments(self, order_id):
        return self.rows(
            """SELECT transaction_id,payment_method_id,transaction_status,amount,fraud_score
            FROM transaction WHERE order_id=%s ORDER BY transaction_id""",
            (order_id,),
        )

    def voucher(self, voucher_id):
        if voucher_id is None:
            return None
        rows = self.rows(
            "SELECT voucher_id,discount_type,discount_value,is_active,is_deleted FROM voucher WHERE voucher_id=%s",
            (voucher_id,),
        )
        return rows[0] if rows else None
