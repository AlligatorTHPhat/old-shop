"""Business invariants shared by all deterministic seed profiles, before any write."""

from collections import Counter
from decimal import Decimal


def validate(data):
    users = {row["user_id"]: row for row in data["users"]}
    products = {row["product_id"]: row for row in data["products"]}
    orders = {row["order_id"]: row for row in data["orders"]}
    images = {row["image_id"]: row for row in data["images"]}
    sold, totals, delivered = Counter(), Counter(), set()
    if len(images) != len(data["images"]) or len(products) != len(data["products"]):
        raise ValueError("Duplicate logical ID")
    for line in data["order_details"]:
        product, order = products[line["product_id"]], orders[line["order_id"]]
        if order["buyer_id"] == product["seller_id"] or line["quantity"] <= 0:
            raise ValueError("Invalid buyer/seller or quantity")
        if product["status"] != 1 or product["is_deleted"]:
            raise ValueError("Order references unpublished product")
        subtotal = Decimal(line["price_at_purchase"]) * line["quantity"]
        if subtotal != Decimal(line["subtotal"]):
            raise ValueError("Invalid line subtotal")
        totals[order["order_id"]] += subtotal
        if order["order_status"] != 4:
            sold[product["product_id"]] += line["quantity"]
        if order["order_status"] == 3:
            delivered.add((order["buyer_id"], product["product_id"]))
    for order in orders.values():
        if order["buyer_id"] not in users or order["contact_id"] != order["buyer_id"]:
            raise ValueError("Invalid contact owner")
        if totals[order["order_id"]] != Decimal(order["total_amount"]):
            raise ValueError("Invalid order total")
        if Decimal(order["final_amount"]) != (
            Decimal(order["total_amount"]) - Decimal(order["discount_amount"]) + Decimal(order["shipping_fee"])
        ):
            raise ValueError("Invalid final amount")
    for product in products.values():
        if product["quantity"] < 0 or product["quantity"] + sold[product["product_id"]] != product["initial_quantity"]:
            raise ValueError("Stock reconciliation failed")
    for review in data["reviews"]:
        if (review["buyer_id"], review["product_id"]) not in delivered:
            raise ValueError("Review requires delivered purchase")
    for annotation in data["metadata"]:
        if images[annotation["image_id"]]["product_id"] != annotation["product_id"]:
            raise ValueError("Image metadata membership mismatch")
    return data
