"""API adapters for bucket mode, keeping the established product/cart/order URLs."""

import base64
import hashlib
import hmac
import json
import uuid
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import ValidationError

from app.api.deps import any_user, customer, get_current_moderator, get_current_user_optional
from app.buckets import catalogue, commerce
from app.buckets.db import execute, one, product_route, rows, transaction
from app.core.config import settings
from app.core.constants import RoleId
from app.models import User
from app.schemas.cart import ShoppingCartItemCreate
from app.schemas.catalog import (
    ImageMetadataInput,
    ProductBase,
    ProductDetailResponse,
    ProductResponse,
    ProductUpdate,
    ReviewCreate,
)
from app.schemas.order import OrderCreate, OrderUpdate
from app.services import image_metadata, neo4j, product_metadata
from app.services.mongo import get_database

router = APIRouter()


def owner(product, user):
    if product["seller_id"] != user.user_id and not user.has_role(RoleId.ADMIN):
        raise HTTPException(403, "Only the seller or admin can edit this listing")


@router.get("/products", response_model=list[ProductResponse])
def products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category_id: int | None = None,
    search: str | None = Query(None, max_length=200),
    sort_by: str = Query("created_at", pattern="^(created_at|price|rating)$"),
    attributes: str | None = None,
    image_search: str | None = Query(None, max_length=200),
    user: User | None = Depends(get_current_user_optional),
):
    ids = product_metadata.matching_ids(product_metadata.parse_filters(attributes)) if attributes is not None else None
    if image_search is not None:
        image_ids = set(image_metadata.matching_image_ids(image_search))
        candidates = get_database().product_details.find(
            {"images.image_id": {"$in": list(image_ids)}}, {"product_id": 1}
        )
        matched = set()
        for candidate in candidates:
            try:
                product = catalogue.get(candidate["product_id"])
                if image_ids.intersection(image["image_id"] for image in product["product_images"]):
                    matched.add(product["product_id"])
            except HTTPException as error:
                if error.status_code != 404:
                    raise
        ids = list(matched) if ids is None else list(set(ids).intersection(matched))
    return catalogue.listing(
        skip=skip,
        limit=limit,
        category_id=category_id,
        search=search,
        sort_by=sort_by,
        exclude_seller=user.user_id if user else None,
        product_ids=ids,
    )


@router.get("/products/seller/my-products", response_model=list[ProductResponse])
def my_products(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), user: User = Depends(any_user)):
    return catalogue.listing(skip=skip, limit=limit, seller_id=user.user_id, public=False)


@router.get("/products/moderation/page")
def moderation_page(
    status: int = Query(..., ge=0, le=2),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    search: str | None = None,
    user: User = Depends(get_current_moderator),
):
    all_items = catalogue.listing(limit=100000, status=status, search=search, public=False)
    return dict(items=all_items[skip : skip + limit], total=len(all_items), skip=skip, limit=limit)


@router.get("/products/moderation/list", response_model=list[ProductResponse])
@router.get("/moderator/products/pending", response_model=list[ProductResponse])
@router.get("/products/pending/all", response_model=list[ProductResponse])
def moderation_list(status: int = 0, user: User = Depends(get_current_moderator)):
    return catalogue.listing(status=status, public=False, limit=1000)


@router.get("/products/{product_id}/related", response_model=list[ProductResponse])
def related(
    product_id: int, limit: int = Query(10, ge=1, le=50), user: User | None = Depends(get_current_user_optional)
):
    catalogue.get(product_id)
    found = []
    from neo4j.exceptions import Neo4jError, ServiceUnavailable

    try:
        candidates = neo4j.related(product_id, limit * 3)
    except (Neo4jError, ServiceUnavailable) as error:
        raise HTTPException(503, "Truy vấn sản phẩm liên quan đang chưa khả dụng.") from error
    for pid in candidates:
        try:
            product = catalogue.get(pid)
            if product["quantity"] > 0 and (not user or product["seller_id"] != user.user_id):
                found.append(product)
        except HTTPException as error:
            if error.status_code != 404:
                raise
    return found[:limit]


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
def detail(product_id: int, user: User | None = Depends(get_current_user_optional)):
    product = catalogue.get(product_id, public=False)
    if not product["visible"] and not (
        user and (product["seller_id"] == user.user_id or user.has_role(RoleId.ADMIN, RoleId.MODERATOR))
    ):
        raise HTTPException(404, "Product not found")
    with transaction() as core:
        product["reviews"] = rows(
            core, "SELECT * FROM review WHERE product_id=%s AND NOT is_deleted AND rating>0", (product_id,)
        )
    response = ProductDetailResponse.model_validate(product)
    response = response.model_copy(update=product_metadata.read(product_id, product["category_id"]))
    return image_metadata.enrich(response)


@router.put("/products/{product_id}/images/metadata")
def edit_metadata(
    product_id: int, entries: list[ImageMetadataInput] = Body(..., max_length=1000), user: User = Depends(any_user)
):
    route = product_route(product_id)
    with transaction(route.site_id, route) as site:
        product = one(site, "SELECT * FROM product WHERE product_id=%s AND NOT is_deleted FOR UPDATE", (product_id,))
        if not product:
            raise HTTPException(404, "Product not found")
        owner(product, user)
        current = {
            row["image_id"]
            for row in rows(site, "SELECT image_id FROM product_image WHERE product_id=%s", (product_id,))
        }
        submitted = [entry.image_id for entry in entries]
        if len(submitted) != len(set(submitted)) or not set(submitted).issubset(current):
            raise HTTPException(422, "Duplicate image or image outside product")
        image_metadata.replace(product_id, entries)
    return {"message": "Đã lưu mô tả ảnh; tìm kiếm đồ thị sẽ được đồng bộ.", "search_sync_status": "pending"}


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    files: list[UploadFile] = File(...),
    category_id: int = Form(...),
    title: str = Form(...),
    price: float = Form(...),
    quantity: int = Form(...),
    description: str | None = Form(None),
    video_url: str | None = Form(None),
    video_file: UploadFile | None = File(None),
    weight_grams: int | None = Form(None),
    dimensions: str | None = Form(None),
    condition_rating: int | None = Form(None),
    warranty_months: int = Form(0),
    transfer_method: int = Form(1),
    idempotency_key: str | None = Header(None),
    user: User = Depends(customer),
):
    from app.services.product_video import normalize_video_link, save_video
    from app.services.storage import save_image

    if not files or len(files) > 20:
        raise HTTPException(422, "Select 1 to 20 images")
    if video_file and video_url:
        raise HTTPException(422, "Choose one video source")
    try:
        data = ProductBase(
            category_id=category_id,
            title=title,
            description=description,
            price=price,
            quantity=quantity,
            video_url=normalize_video_link(video_url),
            weight_grams=weight_grams,
            dimensions=dimensions,
            condition_rating=condition_rating,
            warranty_months=warranty_months,
            transfer_method=transfer_method,
        ).model_dump()
    except ValidationError as error:
        raise HTTPException(422, "Thông tin sản phẩm không hợp lệ.") from error
    digests = []
    for file in [*files, *([video_file] if video_file else [])]:
        digest = hashlib.sha256()
        while chunk := await file.read(65536):
            digest.update(chunk)
        await file.seek(0)
        digests.append(digest.hexdigest())
    data["upload_hashes"] = digests
    product = catalogue.create(user.user_id, data, commerce.operation_id(idempotency_key))
    if not product["product_images"]:
        urls = [await save_image(file, "products", f"prod_{product['product_id']}_{i}") for i, file in enumerate(files)]
        catalogue.add_images(product["product_id"], urls)
    if video_file and not product.get("video_url"):
        video = await save_video(video_file, product["product_id"])
        catalogue.update(product["product_id"], {"video_url": video})
    return catalogue.get(product["product_id"], public=False)


@router.put("/products/{product_id}", response_model=ProductResponse)
def edit_product(product_id: int, body: ProductUpdate, user: User = Depends(any_user)):
    owner(catalogue.get(product_id, public=False), user)
    return catalogue.update(product_id, body.model_dump(exclude_unset=True))


@router.put("/products/{product_id}/listing", response_model=ProductResponse)
async def edit_listing(
    product_id: int,
    details: str = Form(...),
    video_file: UploadFile | None = File(None),
    user: User = Depends(any_user),
):
    from app.services.product_video import normalize_video_link, save_video

    product = catalogue.get(product_id, public=False)
    owner(product, user)
    data = ProductUpdate.model_validate_json(details).model_dump(exclude_unset=True)
    if video_file and "video_url" in data:
        raise HTTPException(422, "Choose one video source")
    if video_file:
        data["video_url"] = await save_video(video_file, product_id)
    elif "video_url" in data:
        data["video_url"] = normalize_video_link(data["video_url"], current_url=product.get("video_url"))
    return catalogue.update(product_id, data)


@router.post("/products/{product_id}/status", response_model=ProductResponse)
def moderate(product_id: int, body: dict = Body(...), user: User = Depends(get_current_moderator)):
    status = body.get("new_status", body.get("status"))
    reason = body.get("reject_reason", body.get("reason"))
    if type(status) is not int or status not in (0, 1, 2) or (status == 2 and not reason):
        raise HTTPException(422, "Invalid moderation state/reason")
    return catalogue.update(
        product_id, dict(status=status, reject_reason=reason if status == 2 else None, approved_by=user.user_id)
    )


@router.patch("/moderator/products/{product_id}/status", response_model=ProductResponse)
def moderator_status(product_id: int, body: dict = Body(...), user: User = Depends(get_current_moderator)):
    return moderate(product_id, body, user)


@router.patch("/products/{product_id}/status")
def seller_status(product_id: int, body: dict = Body(...), user: User = Depends(any_user)):
    owner(catalogue.get(product_id, public=False), user)
    if body.get("new_status") not in (0, 3):
        raise HTTPException(422, "Seller can withdraw or submit for moderation")
    catalogue.update(product_id, {"status": body["new_status"]})
    return {"message": "Đã cập nhật trạng thái"}


@router.delete("/products/{product_id}", status_code=204)
def remove_product(product_id: int, user: User = Depends(any_user)):
    owner(catalogue.get(product_id, public=False), user)
    catalogue.update(product_id, {"is_deleted": True})


@router.delete("/products/{product_id}/images/{image_id}", status_code=204)
def remove_image(product_id: int, image_id: int, user: User = Depends(any_user)):
    owner(catalogue.get(product_id, public=False), user)
    catalogue.delete_image(product_id, image_id)


@router.post("/products/{product_id}/reviews")
def create_review(product_id: int, body: ReviewCreate, user: User = Depends(any_user)):
    product = catalogue.get(product_id)
    if product["seller_id"] == user.user_id:
        raise HTTPException(422, "Cannot review your own product")
    with transaction() as core:
        from app.services.allocation import Allocator

        verified = bool(
            one(
                core,
                'SELECT 1 FROM order_detail d JOIN "order" o USING(order_id) '
                "WHERE d.product_id=%s AND o.buyer_id=%s AND o.order_status=3",
                (product_id, user.user_id),
            )
        )
        row = one(
            core,
            "INSERT INTO review(review_id,product_id,buyer_id,rating,title,content,is_verified_purchase) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                Allocator(core).allocate_ids("review")[0],
                product_id,
                user.user_id,
                body.rating,
                body.title,
                body.content,
                verified,
            ),
        )
    return row


@router.get("/cart")
def get_cart(user: User = Depends(any_user)):
    return commerce.cart(user.user_id)


@router.post("/cart/items", status_code=201)
def add_cart(body: ShoppingCartItemCreate, idempotency_key: str | None = Header(None), user: User = Depends(any_user)):
    return commerce.set_cart(
        user.user_id, body.product_id, body.quantity, commerce.operation_id(idempotency_key), add=True
    )


def own_cart_item(user, item_id):
    with transaction() as core:
        item = one(
            core,
            "SELECT i.* FROM shopping_cart_item i JOIN shopping_cart c USING(cart_id) "
            "WHERE i.cart_item_id=%s AND c.user_id=%s",
            (item_id, user.user_id),
        )
    if not item:
        raise HTTPException(404, "Cart item not found")
    return item


@router.put("/cart/items/{item_id}")
def update_cart(
    item_id: int,
    body: ShoppingCartItemCreate,
    idempotency_key: str | None = Header(None),
    user: User = Depends(any_user),
):
    item = own_cart_item(user, item_id)
    if item["product_id"] != body.product_id:
        raise HTTPException(422, "Cannot change cart item product")
    return commerce.set_cart(user.user_id, item["product_id"], body.quantity, commerce.operation_id(idempotency_key))


@router.delete("/cart/items/{item_id}", status_code=204)
def remove_cart(item_id: int, user: User = Depends(any_user)):
    item = own_cart_item(user, item_id)
    commerce.set_cart(user.user_id, item["product_id"], 0, commerce.operation_id())


@router.delete("/cart", status_code=204)
def clear_cart(user: User = Depends(any_user)):
    for item in commerce.cart(user.user_id)["cart_items"]:
        commerce.set_cart(user.user_id, item["product_id"], 0, commerce.operation_id())


@router.post("/orders", status_code=201)
def place_order(body: OrderCreate, idempotency_key: str | None = Header(None), user: User = Depends(customer)):
    if body.payment_method_id != 1:
        raise HTTPException(422, "Use the PayPal endpoint for online payment")
    return commerce.place(user.user_id, body.model_dump(), commerce.operation_id(idempotency_key))


@router.get("/orders")
def orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status_filter: int | None = None,
    user: User = Depends(customer),
):
    with transaction() as core:
        return rows(
            core,
            'SELECT * FROM "order" WHERE buyer_id=%s AND NOT is_deleted '
            "AND (%s IS NULL OR order_status=%s) ORDER BY order_date DESC,order_id LIMIT %s OFFSET %s",
            (user.user_id, status_filter, status_filter, limit, skip),
        )


@router.get("/orders/seller")
def seller_orders(user: User = Depends(customer)):
    with transaction() as core:
        return rows(
            core,
            'SELECT DISTINCT o.* FROM "order" o JOIN order_detail d USING(order_id) '
            "JOIN catalogue_directory p ON p.product_id=d.product_id WHERE p.seller_id=%s AND NOT o.is_deleted",
            (user.user_id,),
        )


@router.get("/orders/payment-methods")
def payment_methods():
    with transaction() as core:
        return rows(core, "SELECT * FROM payment_method WHERE NOT is_deleted AND payment_method_id IN (1,4)")


@router.get("/orders/check-voucher/{code}")
def check_voucher(code: str, order_amount: Decimal = Query(..., ge=0), user: User = Depends(customer)):
    with transaction() as core:
        voucher = one(
            core,
            "SELECT * FROM voucher WHERE code=%s AND is_active AND NOT is_deleted "
            "AND valid_from<=now() AND valid_to>=now()",
            (code,),
        )
    if (
        not voucher
        or order_amount < (voucher["min_order_amount"] or 0)
        or (voucher["max_usage"] and voucher["usage_count"] >= voucher["max_usage"])
    ):
        raise HTTPException(422, "Voucher unavailable")
    discount = (
        voucher["discount_value"] if voucher["discount_type"] == 0 else order_amount * voucher["discount_value"] / 100
    )
    return {**voucher, "calculated_discount": min(order_amount, discount)}


@router.post("/orders/create-paypal-order")
async def prepare_paypal(body: OrderCreate, idempotency_key: str | None = Header(None), user: User = Depends(customer)):
    from app.services import paypal
    from app.services.fraud_detection import score_transaction

    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_SECRET:
        raise HTTPException(503, "PayPal chưa được cấu hình.")
    if body.payment_method_id != 4:
        raise HTTPException(422, "PayPal payment method required")
    estimate = sum(catalogue.get(item.product_id, public=False)["price"] * item.quantity for item in body.order_items)
    risk = score_transaction(estimate + body.shipping_fee, user.balance)
    if risk.is_fraud or risk.is_suspicious:
        raise HTTPException(403, "Giao dịch cần được kiểm tra trước khi thanh toán.")
    operation = commerce.operation_id(idempotency_key)
    saved = commerce.place(user.user_id, body.model_dump(), operation)
    if saved["order_status"] == 4:
        raise HTTPException(409, "Order cancelled")
    with transaction() as core:
        execute(
            core,
            "INSERT INTO payment_intent(order_id,request_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (saved["order_id"], operation),
        )
        intent = one(core, "SELECT * FROM payment_intent WHERE order_id=%s", (saved["order_id"],))
    if not intent["provider_response"]:
        response = await paypal.create_order(saved["order_id"], saved["final_amount"], uuid.UUID(operation).hex)
        from psycopg2.extras import Json

        with transaction() as core:
            execute(
                core,
                "UPDATE payment_intent SET provider_id=%s,provider_response=%s,state='ready' WHERE order_id=%s",
                (response["id"], Json(response), saved["order_id"]),
            )
    else:
        response = intent["provider_response"]
    return {"paypal": response, "internal_order_id": saved["order_id"]}


@router.post("/orders/{order_id}/capture-paypal")
async def capture_paypal(order_id: int, paypal_order_id: str, user: User = Depends(customer)):
    from app.services import paypal

    with transaction() as core:
        one(core, 'SELECT order_id FROM "order" WHERE order_id=%s FOR UPDATE', (order_id,))
        intent = one(
            core,
            "SELECT i.*,o.buyer_id,o.final_amount,o.order_status FROM payment_intent i "
            'JOIN "order" o USING(order_id) WHERE i.order_id=%s FOR UPDATE OF i',
            (order_id,),
        )
        if not intent or intent["buyer_id"] != user.user_id or intent["provider_id"] != paypal_order_id:
            raise HTTPException(404, "Payment intent not found")
        if intent["state"] == "captured":
            return {"status": "success", "detail": "Thanh toán đã được xác nhận."}
        if intent["order_status"] == 4:
            raise HTTPException(409, "Order cancelled")
        execute(core, "UPDATE payment_intent SET state='capturing' WHERE order_id=%s", (order_id,))
    response = await paypal.capture_order(
        paypal_order_id, uuid.uuid5(uuid.UUID(str(intent["request_id"])), "capture").hex
    )
    captures = [
        capture
        for unit in response.get("purchase_units", [])
        for capture in unit.get("payments", {}).get("captures", [])
    ]
    amount = sum(Decimal(capture.get("amount", {}).get("value", "0")) for capture in captures)
    if (
        response.get("status") != "COMPLETED"
        or response.get("id") != paypal_order_id
        or not captures
        or any(
            capture.get("status") != "COMPLETED" or capture.get("amount", {}).get("currency_code") != "USD"
            for capture in captures
        )
        or amount != Decimal(paypal.vnd_to_usd(intent["final_amount"]))
    ):
        raise HTTPException(409, "Capture chưa được đối soát; giữ trạng thái phục hồi, không giải phóng hàng.")
    with transaction() as core:
        execute(core, "UPDATE payment_intent SET state='captured' WHERE order_id=%s", (order_id,))
        execute(
            core,
            "UPDATE transaction SET transaction_status=1,provider_transaction_id=%s WHERE order_id=%s",
            (paypal_order_id, order_id),
        )
        execute(core, 'UPDATE "order" SET order_status=1 WHERE order_id=%s AND order_status=0', (order_id,))
        execute(core, "UPDATE order_fulfillment SET status=1 WHERE order_id=%s AND status=0", (order_id,))
    return {"status": "success", "detail": "Thanh toán thành công."}


@router.get("/orders/{order_id}")
def get_order(order_id: int, user: User = Depends(any_user)):
    result = commerce.order(order_id)
    if (
        result["buyer_id"] != user.user_id
        and not user.has_role(RoleId.ADMIN)
        and not any(item["product_snapshot"]["seller_id"] == user.user_id for item in result["order_details"])
    ):
        raise HTTPException(403, "Permission denied")
    return result


@router.put("/orders/{order_id}")
def update_order(order_id: int, body: OrderUpdate, user: User = Depends(any_user)):
    saved = get_order(order_id, user)
    if body.order_status == 4:
        if saved["buyer_id"] != user.user_id and not user.has_role(RoleId.ADMIN):
            raise HTTPException(403, "Only buyer/admin can cancel the parent order")
        return commerce.cancel(order_id)
    if saved["buyer_id"] == user.user_id and not user.has_role(RoleId.ADMIN):
        raise HTTPException(403, "Seller/admin required")
    transitions = {0: {1}, 1: {2}, 2: {3}, 3: set(), 4: set()}
    with transaction() as core:
        parent = one(core, 'SELECT order_status FROM "order" WHERE order_id=%s FOR UPDATE', (order_id,))
        if parent["order_status"] == 4:
            raise HTTPException(409, "Order cancelled")
        children = rows(core, "SELECT * FROM order_fulfillment WHERE order_id=%s FOR UPDATE", (order_id,))
        own = [child for child in children if child["seller_id"] == user.user_id or user.has_role(RoleId.ADMIN)]
        if not own or any(body.order_status not in transitions[child["status"]] for child in own):
            raise HTTPException(409, "Invalid fulfillment transition")
        for child in own:
            execute(
                core,
                "UPDATE order_fulfillment SET status=%s WHERE order_id=%s AND seller_id=%s",
                (body.order_status, order_id, child["seller_id"]),
            )
        parent_status = one(core, "SELECT min(status) AS status FROM order_fulfillment WHERE order_id=%s", (order_id,))[
            "status"
        ]
        execute(
            core,
            'UPDATE "order" SET order_status=%s,tracking_number=COALESCE(%s,tracking_number) WHERE order_id=%s',
            (parent_status, body.tracking_number, order_id),
        )
        if parent_status == 3:
            execute(core, "UPDATE transaction SET transaction_status=1 WHERE order_id=%s", (order_id,))
    return commerce.order(order_id)


def cursor_encode(offset, query):
    body = json.dumps(
        dict(offset=offset, query=query, namespace=settings.BUCKET_DATASET, generation=settings.GRAPH_GENERATION),
        sort_keys=True,
    ).encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + body).decode()


@router.get("/images/search")
def search_images(
    q: str = Query(..., min_length=1, max_length=200), limit: int = Query(20, ge=1, le=100), cursor: str | None = None
):
    offset = 0
    if cursor:
        try:
            raw = base64.urlsafe_b64decode(cursor)
            if not hmac.compare_digest(
                raw[:32], hmac.new(settings.SECRET_KEY.encode(), raw[32:], hashlib.sha256).digest()
            ):
                raise ValueError()
            saved = json.loads(raw[32:])
            if (
                saved["query"] != q
                or saved["namespace"] != settings.BUCKET_DATASET
                or saved.get("generation") != settings.GRAPH_GENERATION
            ):
                raise ValueError()
            offset = saved["offset"]
            if type(offset) is not int or not 0 <= offset <= 10000:
                raise ValueError()
        except Exception as error:
            raise HTTPException(422, "Invalid image search cursor") from error
    items, scanned, exhausted = [], 0, False
    while len(items) < limit and scanned < 1000:
        candidates = neo4j.search(q, offset, 100)
        if not candidates:
            exhausted = True
            break
        for candidate in candidates:
            offset += 1
            scanned += 1
            try:
                product = catalogue.get(candidate["product_id"])
                image = next(
                    (image for image in product["product_images"] if image["image_id"] == candidate["image_id"]), None
                )
                if image is None:
                    continue
                metadata = get_database().product_details.find_one(
                    {"product_id": product["product_id"], "deleted": False}
                )
                annotation = next(
                    (
                        entry
                        for entry in (metadata or {}).get("image_metadata", [])
                        if entry["image_id"] == image["image_id"]
                    ),
                    {},
                )
                words = set(
                    neo4j.tokens(" ".join(filter(None, (annotation.get("caption"), annotation.get("description")))))
                )
                if not set(neo4j.tokens(q)).issubset(words):
                    continue
                items.append({**image, **annotation, "product_id": product["product_id"], "score": candidate["score"]})
                if len(items) == limit:
                    break
            except HTTPException as error:
                if error.status_code != 404:
                    raise
        if len(candidates) < 100 and len(items) < limit:
            exhausted = True
            break
    return dict(
        items=items,
        next_cursor=None if exhausted else cursor_encode(offset, q),
        consistency="best_effort",
        search_mode="metadata_tokens",
    )
