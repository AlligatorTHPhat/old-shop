"""Durable order/cart intents and site-local, idempotent stock reservations."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from psycopg2.extras import Json

from app.buckets import catalogue
from app.buckets.db import execute, one, product_route, rows, transaction
from app.services.allocation import Allocator, canonical


def operation_id(value=None):
    try:
        return str(uuid.UUID(str(value))) if value else str(uuid.uuid4())
    except ValueError as error:
        raise HTTPException(422, "Idempotency-Key must be a UUID") from error


def child_id(parent, name):
    return str(uuid.uuid5(uuid.UUID(str(parent)), str(name)))


def stock(reservation_id: str, product_id: int, buyer_id: int, quantity: int, action: str, operation: str) -> dict:
    route = product_route(product_id)
    digest = hashlib.sha256(canonical([reservation_id, product_id, buyer_id, quantity, action]).encode()).hexdigest()
    with transaction(route.site_id, route) as site:
        # All stock operations lock the parent first, including retry, release and commit.
        product = one(site, "SELECT * FROM product WHERE product_id=%s FOR UPDATE", (product_id,))
        prior = one(site, "SELECT * FROM stock_operation WHERE operation_id=%s", (operation,))
        if prior:
            if prior["request_hash"] != digest:
                raise HTTPException(409, "Stock idempotency key reused")
            return prior["result"]
        reservation = one(site, "SELECT * FROM stock_reservation WHERE reservation_id=%s FOR UPDATE", (reservation_id,))
        if reservation and (reservation["buyer_id"] != buyer_id or reservation["product_id"] != product_id):
            raise HTTPException(409, "Reservation owner mismatch")
        if action == "hold":
            if product["is_deleted"] or product["seller_id"] == buyer_id or product["status"] not in (1, 3):
                raise HTTPException(422, "Product cannot be reserved")
            if reservation and reservation["state"] == "committed":
                raise HTTPException(409, "Reservation already committed")
            held = reservation["quantity"] if reservation and reservation["state"] == "held" else 0
            delta = quantity - held
            if quantity < 0 or delta > product["quantity"]:
                raise HTTPException(409, "Insufficient stock")
            price = reservation["price"] if reservation else product["price"]
            execute(
                site,
                "UPDATE product SET quantity=quantity-%s,status=CASE WHEN quantity-%s=0 THEN 3 "
                "WHEN status=3 THEN 1 ELSE status END WHERE product_id=%s",
                (delta, delta, product_id),
            )
            execute(
                site,
                "INSERT INTO "
                "stock_reservation(reservation_id,operation_id,product_id,buyer_id,quantity,price,state,expires_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(reservation_id) DO UPDATE "
                "SET quantity=excluded.quantity,state=excluded.state,expires_at=excluded.expires_at",
                (
                    reservation_id,
                    operation,
                    product_id,
                    buyer_id,
                    max(quantity, 1),
                    price,
                    "held" if quantity else "released",
                    datetime.now(UTC) + timedelta(hours=24),
                ),
            )
        elif action in ("commit", "release"):
            if not reservation:
                if action == "commit":
                    raise HTTPException(409, "Reservation missing")
            elif action == "commit":
                if reservation["state"] == "released":
                    raise HTTPException(409, "Reservation expired or released")
                execute(
                    site, "UPDATE stock_reservation SET state='committed' WHERE reservation_id=%s", (reservation_id,)
                )
            elif reservation["state"] != "released":
                execute(
                    site,
                    "UPDATE product SET quantity=quantity+%s,status=CASE WHEN status=3 THEN 1 ELSE status END "
                    "WHERE product_id=%s",
                    (reservation["quantity"], product_id),
                )
                execute(
                    site, "UPDATE stock_reservation SET state='released' WHERE reservation_id=%s", (reservation_id,)
                )
        else:
            raise ValueError("Unknown stock operation")
        result = one(
            site,
            "SELECT reservation_id,product_id,buyer_id,quantity,price,state FROM stock_reservation "
            "WHERE reservation_id=%s",
            (reservation_id,),
        )
        encoded = __import__("json").loads(canonical(result or {}))
        execute(
            site,
            "INSERT INTO stock_operation(operation_id,request_hash,result) VALUES(%s,%s,%s)",
            (operation, digest, Json(encoded)),
        )
        return encoded


def cart(user_id: int) -> dict:
    with transaction() as core:
        found = one(core, "SELECT * FROM shopping_cart WHERE user_id=%s", (user_id,))
        if not found:
            found = one(core, "INSERT INTO shopping_cart(user_id) VALUES(%s) RETURNING *", (user_id,))
        items = rows(
            core, "SELECT * FROM shopping_cart_item WHERE cart_id=%s ORDER BY cart_item_id", (found["cart_id"],)
        )
    for item in items:
        item["product"] = catalogue.get(item["product_id"], public=False, include_deleted=True)
    return {**found, "cart_items": items}


def set_cart(user_id: int, product_id: int, quantity: int, operation: str, add=False) -> dict | None:
    digest = hashlib.sha256(canonical([product_id, quantity, add]).encode()).hexdigest()
    with transaction() as core:
        execute(core, "SELECT pg_advisory_xact_lock(%s)", (user_id,))
        prior = one(core, "SELECT * FROM commerce_operation WHERE operation_id=%s", (operation,))
        if prior:
            if prior["user_id"] != user_id or prior["request_hash"] != digest:
                raise HTTPException(409, "Idempotency key reused")
            if prior["state"] == "done":
                return prior["result"]
            intent = prior["payload"]
        else:
            if one(
                core,
                "SELECT operation_id FROM commerce_operation WHERE user_id=%s AND state NOT IN ('done','failed')",
                (user_id,),
            ):
                raise HTTPException(409, "A pending operation must be recovered first")
            current_cart = one(core, "SELECT * FROM shopping_cart WHERE user_id=%s", (user_id,))
            if not current_cart:
                current_cart = one(core, "INSERT INTO shopping_cart(user_id) VALUES(%s) RETURNING *", (user_id,))
            item = one(
                core,
                "SELECT * FROM shopping_cart_item WHERE cart_id=%s AND product_id=%s",
                (current_cart["cart_id"], product_id),
            )
            desired = quantity + (item["quantity"] if item and add else 0)
            intent = dict(
                product_id=product_id,
                quantity=desired,
                cart_id=current_cart["cart_id"],
                requested_quantity=quantity,
                add=add,
                reservation_id=str(item["reservation_id"]) if item else str(uuid.uuid4()),
            )
            execute(
                core,
                "INSERT INTO commerce_operation(operation_id,user_id,kind,request_hash,state,payload) "
                "VALUES(%s,%s,'cart',%s,'pending',%s)",
                (operation, user_id, digest, Json(intent)),
            )
    try:
        stock(
            intent["reservation_id"],
            product_id,
            user_id,
            intent["quantity"],
            "hold" if intent["quantity"] else "release",
            operation,
        )
    except HTTPException as error:
        if error.status_code < 500:
            with transaction() as core:
                execute(core, "UPDATE commerce_operation SET state='failed' WHERE operation_id=%s", (operation,))
        raise
    with transaction() as core:
        execute(core, "SELECT pg_advisory_xact_lock(%s)", (user_id,))
        if intent["quantity"]:
            result = one(
                core,
                "INSERT INTO shopping_cart_item(cart_id,product_id,quantity,reservation_id) "
                "VALUES(%s,%s,%s,%s) ON CONFLICT(cart_id,product_id) DO UPDATE "
                "SET quantity=excluded.quantity,reservation_id=excluded.reservation_id RETURNING *",
                (intent["cart_id"], product_id, intent["quantity"], intent["reservation_id"]),
            )
        else:
            execute(
                core,
                "DELETE FROM shopping_cart_item WHERE cart_id=%s AND product_id=%s",
                (intent["cart_id"], product_id),
            )
            result = None
        serialized = __import__("json").loads(canonical(result))
        execute(
            core,
            "UPDATE commerce_operation SET state='done',result=%s WHERE operation_id=%s",
            (Json(serialized), operation),
        )
    if result:
        result["product"] = catalogue.get(product_id, public=False)
    return result


def _place(user_id: int, body: dict, operation: str) -> dict:
    request_hash = hashlib.sha256(canonical(body).encode()).hexdigest()
    with transaction() as core:
        execute(core, "SELECT pg_advisory_xact_lock(%s)", (user_id,))
        prior = one(core, "SELECT * FROM commerce_operation WHERE operation_id=%s FOR UPDATE", (operation,))
        if prior:
            if prior["user_id"] != user_id or prior["request_hash"] != request_hash:
                raise HTTPException(409, "Idempotency key reused")
            if prior["state"] == "done":
                return order(prior["result"]["order_id"])
            if prior["state"] == "failed":
                raise HTTPException(409, "Order was compensated; use a new request key")
            intent = prior["payload"]
        else:
            if one(
                core,
                "SELECT operation_id FROM commerce_operation WHERE user_id=%s AND state NOT IN ('done','failed')",
                (user_id,),
            ):
                raise HTTPException(409, "A pending operation must be recovered first")
            contact = one(
                core,
                "SELECT * FROM contact_info WHERE contact_id=%s AND user_id=%s AND NOT is_deleted",
                (body["contact_id"], user_id),
            )
            if not contact:
                raise HTTPException(422, "Contact does not belong to buyer")
            if body["payment_method_id"] not in (1, 4):
                raise HTTPException(422, "Supported payment methods: COD or PayPal")
            ids = [line["product_id"] for line in body["order_items"]]
            if len(ids) != len(set(ids)) or not ids:
                raise HTTPException(422, "Duplicate or empty order items")
            lines = []
            for line in body["order_items"]:
                product = catalogue.get(line["product_id"], public=False)
                if product["seller_id"] == user_id or not product["trade_allowed"] or product["status"] not in (1, 3):
                    raise HTTPException(422, "Product cannot be ordered")
                cart_item = one(
                    core,
                    "SELECT i.* FROM shopping_cart_item i JOIN shopping_cart c USING(cart_id) "
                    "WHERE c.user_id=%s AND i.product_id=%s",
                    (user_id, line["product_id"]),
                )
                if cart_item and cart_item["quantity"] != line["quantity"]:
                    raise HTTPException(422, "Update cart quantity before checkout")
                lines.append(
                    {
                        **line,
                        "reservation_id": str(cart_item["reservation_id"])
                        if cart_item
                        else child_id(operation, line["product_id"]),
                        "from_cart": bool(cart_item),
                        "product": __import__("json").loads(canonical(product)),
                    }
                )
            intent = dict(
                body=__import__("json").loads(canonical(body)),
                lines=lines,
                order_id=Allocator(core).allocate_ids("order")[0],
                address=body.get("shipping_address") or contact["address"],
            )
            execute(
                core,
                "INSERT INTO commerce_operation(operation_id,user_id,kind,request_hash,state,payload) "
                "VALUES(%s,%s,'order',%s,'pending',%s)",
                (operation, user_id, request_hash, Json(intent)),
            )
    try:
        reservations = []
        for line in intent["lines"]:
            reservations.append(
                stock(
                    line["reservation_id"],
                    line["product_id"],
                    user_id,
                    line["quantity"],
                    "hold",
                    child_id(operation, f"hold:{line['product_id']}"),
                )
            )
    except HTTPException as error:
        if error.status_code < 500:
            with transaction() as core:
                execute(core, "UPDATE commerce_operation SET state='compensating' WHERE operation_id=%s", (operation,))
            compensate(operation)
        raise
    with transaction() as core:
        execute(core, "SELECT pg_advisory_xact_lock(%s)", (user_id,))
        oid = intent["order_id"]
        existing_order = one(core, 'SELECT order_id FROM "order" WHERE order_id=%s', (oid,))
        if not existing_order:
            total = sum(Decimal(reservation["price"]) * reservation["quantity"] for reservation in reservations)
            discount, voucher_id = Decimal(0), None
            if body.get("voucher_code"):
                voucher = one(
                    core,
                    "SELECT * FROM voucher WHERE code=%s AND NOT is_deleted AND is_active "
                    "AND valid_from<=now() AND valid_to>=now() FOR UPDATE",
                    (body["voucher_code"],),
                )
                if (
                    not voucher
                    or total < (voucher["min_order_amount"] or 0)
                    or (voucher["max_usage"] and voucher["usage_count"] >= voucher["max_usage"])
                ):
                    raise HTTPException(422, "Voucher unavailable")
                discount = min(
                    total,
                    voucher["discount_value"]
                    if voucher["discount_type"] == 0
                    else total * voucher["discount_value"] / 100,
                )
                voucher_id = voucher["voucher_id"]
                execute(core, "UPDATE voucher SET usage_count=usage_count+1 WHERE voucher_id=%s", (voucher_id,))
            final = total - discount + Decimal(str(body["shipping_fee"]))
            execute(
                core,
                'INSERT INTO "order"(order_id,buyer_id,contact_id,payment_method_id,total_amount,shipping_fee,'
                "discount_amount,final_amount,shipping_address,notes,voucher_id,operation_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    oid,
                    user_id,
                    body["contact_id"],
                    body["payment_method_id"],
                    total,
                    body["shipping_fee"],
                    discount,
                    final,
                    intent["address"],
                    body.get("notes"),
                    voucher_id,
                    operation,
                ),
            )
            for line, reservation in zip(intent["lines"], reservations, strict=True):
                lid = Allocator(core).allocate_ids("order_detail")[0]
                execute(
                    core,
                    "INSERT INTO "
                    "order_detail(order_detail_id,order_id,product_id,quantity,price_at_purchase,subtotal,"
                    "product_snapshot,reservation_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        lid,
                        oid,
                        line["product_id"],
                        line["quantity"],
                        reservation["price"],
                        Decimal(reservation["price"]) * line["quantity"],
                        Json(line["product"]),
                        line["reservation_id"],
                    ),
                )
            execute(
                core,
                "INSERT INTO "
                "transaction(order_id,user_id,payment_method_id,amount,reference_number) VALUES(%s,%s,%s,%s,%s)",
                (oid, user_id, body["payment_method_id"], final, f"bucket-{operation}"),
            )
            for line in intent["lines"]:
                execute(
                    core,
                    "INSERT INTO order_fulfillment(order_id,seller_id,bucket_id) VALUES(%s,%s,%s) "
                    "ON CONFLICT DO NOTHING",
                    (oid, line["product"]["seller_id"], line["product"]["bucket_id"]),
                )
        execute(core, "UPDATE commerce_operation SET state='committing' WHERE operation_id=%s", (operation,))
    for line in intent["lines"]:
        stock(
            line["reservation_id"],
            line["product_id"],
            user_id,
            line["quantity"],
            "commit",
            child_id(operation, f"commit:{line['product_id']}"),
        )
    with transaction() as core:
        execute(
            core,
            "DELETE FROM shopping_cart_item WHERE cart_id IN (SELECT cart_id FROM shopping_cart WHERE user_id=%s) "
            "AND product_id=ANY(%s)",
            (user_id, [line["product_id"] for line in intent["lines"]]),
        )
        execute(
            core,
            "UPDATE commerce_operation SET state='done',result=%s WHERE operation_id=%s",
            (Json({"order_id": intent["order_id"]}), operation),
        )
    return order(intent["order_id"])


def place(user_id: int, body: dict, operation: str) -> dict:
    try:
        return _place(user_id, body, operation)
    except HTTPException as error:
        if error.status_code < 500:
            with transaction() as core:
                saved = one(core, "SELECT * FROM commerce_operation WHERE operation_id=%s", (operation,))
                created = one(core, 'SELECT order_id FROM "order" WHERE operation_id=%s', (operation,))
                if saved and not created and saved["state"] not in ("done", "failed"):
                    execute(
                        core, "UPDATE commerce_operation SET state='compensating' WHERE operation_id=%s", (operation,)
                    )
            if saved and not created and saved["state"] not in ("done", "failed"):
                compensate(operation)
        raise


def compensate(operation: str):
    with transaction() as core:
        saved = one(core, "SELECT * FROM commerce_operation WHERE operation_id=%s", (operation,))
    for line in saved["payload"]["lines"]:
        if not line["from_cart"]:
            stock(
                line["reservation_id"],
                line["product_id"],
                saved["user_id"],
                0,
                "release",
                child_id(operation, f"undo:{line['product_id']}"),
            )
    with transaction() as core:
        execute(core, "UPDATE commerce_operation SET state='failed' WHERE operation_id=%s", (operation,))


def order(order_id: int) -> dict:
    with transaction() as core:
        result = one(core, 'SELECT * FROM "order" WHERE order_id=%s AND NOT is_deleted', (order_id,))
        if not result:
            raise HTTPException(404, "Order not found")
        result["order_details"] = rows(
            core, "SELECT * FROM order_detail WHERE order_id=%s ORDER BY order_detail_id", (order_id,)
        )
    for line in result["order_details"]:
        line["product"] = line["product_snapshot"]
    return result


def cancel(order_id: int):
    saved = order(order_id)
    if saved["order_status"] not in (0, 1, 4):
        raise HTTPException(409, "Only pending/confirmed orders can be cancelled")
    op = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bucket-cancel:{order_id}"))
    with transaction() as core:
        locked = one(core, 'SELECT order_status,voucher_id FROM "order" WHERE order_id=%s FOR UPDATE', (order_id,))
        if locked["order_status"] not in (0, 1, 4):
            raise HTTPException(409, "Order has advanced beyond cancellation")
        if locked["order_status"] != 4 and any(line["reservation_id"] is None for line in saved["order_details"]):
            raise HTTPException(409, "Historical stock must be reconciled before cancelling this imported order")
        paid = one(
            core, "SELECT * FROM payment_intent WHERE order_id=%s AND state IN ('capturing','captured')", (order_id,)
        )
        if paid:
            raise HTTPException(409, "Payment capture/refund must be reconciled before cancellation")
        execute(
            core,
            "INSERT INTO commerce_operation(operation_id,user_id,kind,request_hash,state,payload) "
            "VALUES(%s,%s,'cancel',%s,'pending',%s) ON CONFLICT DO NOTHING",
            (op, saved["buyer_id"], str(order_id), Json({"order_id": order_id})),
        )
        execute(core, 'UPDATE "order" SET order_status=4 WHERE order_id=%s', (order_id,))
        if locked["order_status"] != 4 and locked["voucher_id"] is not None:
            execute(
                core,
                "UPDATE voucher SET usage_count=GREATEST(usage_count-1,0) WHERE voucher_id=%s",
                (locked["voucher_id"],),
            )
    for line in saved["order_details"]:
        if line["reservation_id"]:
            stock(
                str(line["reservation_id"]),
                line["product_id"],
                saved["buyer_id"],
                0,
                "release",
                child_id(op, line["product_id"]),
            )
    with transaction() as core:
        execute(core, "UPDATE order_fulfillment SET status=4 WHERE order_id=%s", (order_id,))
        execute(core, "UPDATE commerce_operation SET state='done' WHERE operation_id=%s", (op,))
        execute(core, "UPDATE transaction SET transaction_status=3 WHERE order_id=%s", (order_id,))
    return order(order_id)


def recover():
    with transaction() as core:
        pending = rows(
            core, "SELECT * FROM commerce_operation WHERE state NOT IN ('done','failed') ORDER BY updated_at"
        )
    results = []
    for intent in pending:
        op = str(intent["operation_id"])
        try:
            if intent["state"] == "compensating":
                compensate(op)
            elif intent["kind"] == "cancel":
                cancel(intent["payload"]["order_id"])
            elif intent["kind"] == "cart":
                payload = intent["payload"]
                # Use the original intent; set_cart ignores computed quantity on resume.
                set_cart(intent["user_id"], payload["product_id"], payload["requested_quantity"], op, payload["add"])
            else:
                place(intent["user_id"], intent["payload"]["body"], op)
            results.append({"operation_id": op, "state": "recovered"})
        except Exception as error:
            results.append({"operation_id": op, "error_code": type(error).__name__})
    return results


def expire_reservations(limit=100):
    """Release abandoned carts while protecting reservations referenced by an order saga."""
    with transaction() as core:
        sites = rows(core, "SELECT site_id FROM site_registry WHERE active")
    count = 0
    for site in sites:
        with transaction(site["site_id"]) as connection:
            expired = rows(
                connection,
                "SELECT r.* FROM stock_reservation r JOIN product p USING(product_id) "
                "JOIN bucket_lease l USING(bucket_id) WHERE r.state='held' AND r.expires_at<now() "
                "AND l.state='active' LIMIT %s",
                (limit,),
            )
        for reservation in expired:
            with transaction() as core:
                execute(core, "SELECT pg_advisory_xact_lock(%s)", (reservation["buyer_id"],))
                if one(
                    core,
                    "SELECT 1 FROM commerce_operation WHERE user_id=%s AND state NOT IN ('done','failed')",
                    (reservation["buyer_id"],),
                ):
                    continue
                operation = child_id(reservation["reservation_id"], "expiry")
                stock(
                    str(reservation["reservation_id"]),
                    reservation["product_id"],
                    reservation["buyer_id"],
                    0,
                    "release",
                    operation,
                )
                execute(
                    core, "DELETE FROM shopping_cart_item WHERE reservation_id=%s", (reservation["reservation_id"],)
                )
                count += 1
    return count
