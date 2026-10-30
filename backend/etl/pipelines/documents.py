"""Product, order, review, audit and contact projections with strict ownership."""

from datetime import UTC, datetime, timedelta

from app.schemas.documents import DOCUMENT_MODELS
from app.services.storage import bucket_for, validate_path
from etl.extract import SOURCES
from etl.transform import QualityError, dimensions, document_id, label, public_text, utc, video_url, vnd

# These fields belong to Mongo; neither full load nor replay can overwrite them.
OWNED = {
    "product_details": {"attributes", "tags"},
    "reviews": {"status", "moderation", "evidence"},
    "contact_messages": {"attachments"},
}


def project(source, entity, key, run_id, now=None):
    now = now or datetime.now(UTC)
    row = source.get(entity, key)
    if row is None:
        return None
    origins = source.origins(entity, row["_source_key"])

    def time(field):
        return utc(row.get(field), origins.get(field))

    data = {"_id": document_id(entity, key), "etl": {"synced_at": now, "run_id": str(run_id)}}
    data["deleted"] = bool(row.get("is_deleted", False))
    if entity == "product":
        images = []
        for image in source.images(row["product_id"]):
            if not image["image_url"].startswith("/media/products/"):
                raise QualityError("unsupported_image_reference")
            path = validate_path(image["image_url"].removeprefix("/media/"))
            images.append(
                dict(
                    bucket=bucket_for(path),
                    key=path,
                    image_id=image["image_id"],
                    content_type=image["content_type"],
                    size=image["size_bytes"],
                    is_primary=image["is_primary"],
                    display_order=image["display_order"],
                )
            )
        data.update(
            product_id=row["product_id"],
            category_id=row["category_id"],
            description=public_text(row["description"]),
            video_url=video_url(row["video_url"]),
            weight_grams=row["weight_grams"],
            dimensions=dimensions(row["dimensions"]),
            dimensions_raw=public_text(row["dimensions"]),
            condition=None
            if row["condition_rating"] is None
            else {"grade": row["condition_rating"], "warranty_months": row["warranty_months"] or 0},
            images=images,
            updated_at=time("updated_at") or time("created_at"),
        )
        data["etl"]["source_updated_at"] = data["updated_at"]
    elif entity == "order":
        items = [
            dict(
                product_id=item["product_id"],
                quantity=item["quantity"],
                price_at_purchase_vnd=vnd(item["price_at_purchase"]),
                subtotal_vnd=vnd(item["subtotal"]),
                title_current=public_text(item["title"]),
                category_id_current=item["category_id"],
                seller_id_current=item["seller_id"],
            )
            for item in source.items(row["order_id"])
        ]
        if not items:
            raise QualityError("empty_or_orphan_order")
        if any(item["subtotal_vnd"] != item["quantity"] * item["price_at_purchase_vnd"] for item in items):
            raise QualityError("item_subtotal_mismatch")
        payments = [
            dict(
                transaction_id=payment["transaction_id"],
                method_id=payment["payment_method_id"],
                status_code=payment["transaction_status"],
                amount_vnd=vnd(payment["amount"]),
                fraud_score=float(payment["fraud_score"]) if payment["fraud_score"] is not None else None,
            )
            for payment in source.payments(row["order_id"])
        ]
        totals = {
            name + "_vnd": vnd(row[name])
            for name in ("total_amount", "shipping_fee", "discount_amount", "final_amount")
        }
        if sum(item["subtotal_vnd"] for item in items) != totals["total_amount_vnd"]:
            raise QualityError("order_total_mismatch")
        if (
            totals["total_amount_vnd"] + totals["shipping_fee_vnd"] - totals["discount_amount_vnd"]
            != totals["final_amount_vnd"]
        ):
            raise QualityError("order_final_mismatch")
        voucher = source.voucher(row["voucher_id"])
        if row["voucher_id"] is not None and voucher is None:
            raise QualityError("orphan_voucher")
        data.update(
            order_id=row["order_id"],
            buyer={"id": row["buyer_id"], "region": "unknown"},
            items=items,
            payments=payments,
            **totals,
            voucher_id=row["voucher_id"],
            voucher_current=None
            if voucher is None
            else dict(
                voucher_id=voucher["voucher_id"],
                discount_type_code_current=voucher["discount_type"],
                discount_value_current=str(voucher["discount_value"]),
                is_active_current=voucher["is_active"],
                is_deleted_current=voucher["is_deleted"],
            ),
            order_status=row["order_status"],
            order_date=time("order_date"),
        )
    elif entity == "review":
        data.update(
            review_id=row["review_id"],
            product_id=row["product_id"],
            buyer_id=row["buyer_id"],
            type="report" if row["rating"] == 0 else "review",
            rating=row["rating"],
            title=public_text(row["title"]),
            content=public_text(row["content"]),
            created_at=time("created_at"),
            updated_at=time("updated_at"),
        )
    elif entity == "system_log":
        data["etl"]["source_created_at"] = document_id(entity, key).split(":", 2)[2]
        data.update(
            log_id=row["log_id"],
            actor_id=row["user_id"],
            action=label(row["action"]),
            resource_type=label(row["resource_type"]) if row["resource_type"] else None,
            resource_id=row["resource_id"],
            created_at=time("created_at"),
            payload={"event": "PG_LOG"},
        )
        if data["created_at"] < now - timedelta(days=90):
            return None
    elif entity == "violation_log":
        data.update(
            log_id=row["log_id"],
            target_user_id=row["user_id"],
            action_taken=label(row["action_taken"]),
            reason="Violation details retained in PostgreSQL",
            created_at=time("created_at"),
        )
    else:
        data.update(
            feedback_id=row["feedback_id"],
            user_id=row["user_id"],
            status=row["status"],
            subject="Contact request",
            content="Message retained in PostgreSQL",
            created_at=time("created_at"),
        )
    collection = SOURCES[entity][2]
    model = DOCUMENT_MODELS[collection].model_validate(data)
    return model.model_dump(by_alias=True)
