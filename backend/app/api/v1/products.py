import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import any_user, customer, get_current_moderator, get_current_user, get_current_user_optional, get_db
from app.core.constants import ProductStatus, RoleId
from app.crud.category import crud_category
from app.crud.product import crud_product
from app.models import Product, ProductImage, User
from app.schemas import (
    Message,
    ProductDetailResponse,
    ProductResponse,
    ProductUpdate,
    ReviewCreate,
    ReviewResponse,
    StatusUpdate,
)
from app.schemas.catalog import ModerationProductPage
from app.services import product_metadata
from app.services.product_video import cleanup_replaced_video, discard_video, normalize_video_link, save_video
from app.services.storage import delete_media, save_image

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


def _get_or_404(db: Session, product_id: int) -> Product:
    product = crud_product.get_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


def _ensure_owner_or_admin(product: Product, user: User) -> None:
    if product.seller_id != user.user_id and not user.has_role(RoleId.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only seller or admin can modify this product"
        )


# ---------- catalogue ----------


@router.get("", response_model=list[ProductResponse])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category_id: int | None = Query(None),
    search: str | None = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at|price|rating)$"),
    attributes: str | None = Query(None, max_length=4096, description='JSON equality filters, e.g. {"ram_gb":8}'),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Approved products. Logged-in sellers don't see their own listings."""
    ids = product_metadata.matching_ids(product_metadata.parse_filters(attributes)) if attributes is not None else None
    return crud_product.catalogue(
        db,
        skip=skip,
        limit=limit,
        category_id=category_id,
        search=search,
        sort_by=sort_by,
        exclude_seller=current_user.user_id if current_user else None,
        product_ids=ids,
    )


@router.get("/seller/my-products", response_model=list[ProductResponse])
def get_my_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(any_user),
    db: Session = Depends(get_db),
):
    return crud_product.get_by_seller(db, current_user.user_id, skip=skip, limit=limit)


@router.get("/moderation/list", response_model=list[ProductResponse])
def list_products_by_status(
    status: int = Query(..., description="0: Pending, 1: Approved, 2: Rejected"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    moderator: User = Depends(get_current_moderator),
    db: Session = Depends(get_db),
):
    return crud_product.get_by_status(db, status, skip=skip, limit=limit)


@router.get("/moderation/page", response_model=ModerationProductPage)
def moderation_product_page(
    status: int = Query(..., ge=0, le=2, description="0: Pending, 1: Approved, 2: Rejected"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    search: str | None = Query(None, max_length=200),
    moderator: User = Depends(get_current_moderator),
    db: Session = Depends(get_db),
):
    products, total = crud_product.moderation_page(db, status, skip=skip, limit=limit, search=search)
    return {
        "items": [
            {
                **ProductResponse.model_validate(product).model_dump(),
                "seller_name": product.seller.username,
                "category_name": product.category.name,
            }
            for product in products
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/pending/all", response_model=list[ProductResponse])
def get_pending_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    moderator: User = Depends(get_current_moderator),
    db: Session = Depends(get_db),
):
    return crud_product.get_by_status(db, ProductStatus.PENDING, skip=skip, limit=limit)


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = _get_or_404(db, product_id)
    crud_product.increment_view_count(db, product)
    response = ProductDetailResponse.model_validate(product)
    return response.model_copy(update=product_metadata.read(product.product_id, product.category_id))


# ---------- seller actions ----------


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    files: list[UploadFile] = File(...),
    category_id: int = Form(...),
    title: str = Form(...),
    description: str | None = Form(None),
    price: float = Form(...),
    quantity: int = Form(...),
    video_url: str | None = Form(None),
    video_file: UploadFile | None = File(None),
    weight_grams: int | None = Form(None),
    dimensions: str | None = Form(None),
    condition_rating: int | None = Form(None),
    warranty_months: int = Form(0),
    transfer_method: int = Form(1),
    current_user: User = Depends(customer),
    db: Session = Depends(get_db),
):
    """Create a listing (multipart). It stays pending until a moderator approves it."""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image file is required")
    if video_file is not None and video_url and video_url.strip():
        raise HTTPException(400, "Chỉ chọn liên kết video hoặc file MP4.")
    video_url = normalize_video_link(video_url)
    if not crud_category.get_by_id(db, category_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found")

    product = crud_product.add_pending(
        db,
        {
            "seller_id": current_user.user_id,
            "category_id": category_id,
            "title": title,
            "description": description,
            "price": price,
            "quantity": quantity,
            "video_url": video_url,
            "weight_grams": weight_grams,
            "dimensions": dimensions,
            "condition_rating": condition_rating,
            "warranty_months": warranty_months,
            "transfer_method": transfer_method,
        },
    )

    saved: list[str] = []
    saved_video = None
    try:
        if video_file is not None:
            saved_video = await save_video(video_file, product.product_id)
            product.video_url = saved_video
        for index, file in enumerate(files, start=1):
            saved.append(await save_image(file, "products", f"prod_{product.product_id}_{index}"))
        await run_in_threadpool(crud_product.add_images, db, product, saved)
        db.commit()
    except Exception:
        db.rollback()
        discard_video(saved_video)
        for url in saved:
            await run_in_threadpool(delete_media, url)
        raise

    db.refresh(product)
    logger.info("Product submitted", extra={"product_id": product.product_id, "seller_id": current_user.user_id})
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_update: ProductUpdate,
    current_user: User = Depends(any_user),
    db: Session = Depends(get_db),
):
    product = _editable_product(db, product_id, current_user)
    return _save_listing(db, product, product_update)


def _editable_product(db: Session, product_id: int, user: User) -> Product:
    # Serialize replacements, preventing an older concurrent request from deleting a new video.
    product = (
        db.query(Product)
        .filter(Product.product_id == product_id, Product.is_deleted.is_(False))
        .with_for_update()
        .first()
    )
    if not product:
        raise HTTPException(404, "Product not found")
    _ensure_owner_or_admin(product, user)
    return product


def _save_listing(db: Session, product: Product, product_update: ProductUpdate, uploaded: str | None = None) -> Product:
    old_video = product.video_url
    try:
        new_category = product_update.category_id
        if new_category and new_category != product.category_id and not crud_category.get_by_id(db, new_category):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found")
        values = product_update.model_dump(exclude_unset=True)
        if uploaded is not None:
            values["video_url"] = uploaded
        elif "video_url" in values:
            values["video_url"] = normalize_video_link(values["video_url"], current_url=old_video)
        for key, value in values.items():
            if value is not None or key == "video_url":
                setattr(product, key, value)
        db.commit()
    except Exception:
        db.rollback()
        discard_video(uploaded)
        raise
    # A failed refresh after commit must never cause deletion of the now-referenced upload.
    db.refresh(product)
    cleanup_replaced_video(db, old_video, product.video_url)
    return product


@router.put("/{product_id}/listing", response_model=ProductResponse)
async def update_listing(
    product_id: int,
    details: str = Form(..., description="JSON ProductUpdate; omit video_url to keep, null to remove"),
    video_file: UploadFile | None = File(None),
    current_user: User = Depends(any_user),
    db: Session = Depends(get_db),
):
    """Atomically update listing fields and optionally replace its MP4."""
    try:
        data = ProductUpdate.model_validate_json(details)
    except ValidationError as exc:
        raise HTTPException(422, "Thông tin sản phẩm không hợp lệ.") from exc
    if video_file is not None and "video_url" in data.model_fields_set:
        raise HTTPException(400, "Chỉ chọn liên kết video hoặc file MP4.")
    product = _editable_product(db, product_id, current_user)
    uploaded = await save_video(video_file, product_id) if video_file is not None else None
    return _save_listing(db, product, data, uploaded)


@router.patch("/{product_id}/status", response_model=Message)
def change_product_status(
    product_id: int,
    status_data: StatusUpdate,
    current_user: User = Depends(any_user),
    db: Session = Depends(get_db),
):
    """Seller hides/re-lists their own product."""
    product = _get_or_404(db, product_id)
    if product.seller_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền")
    product.status = status_data.new_status
    db.commit()
    return Message(message="Cập nhật trạng thái thành công")


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, current_user: User = Depends(any_user), db: Session = Depends(get_db)):
    product = _get_or_404(db, product_id)
    _ensure_owner_or_admin(product, current_user)
    crud_product.soft_delete(db, product)


@router.delete("/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_image(
    product_id: int, image_id: int, current_user: User = Depends(any_user), db: Session = Depends(get_db)
):
    product = _get_or_404(db, product_id)
    _ensure_owner_or_admin(product, current_user)
    image = db.query(ProductImage).filter_by(product_id=product_id, image_id=image_id).first()
    if image is None:
        raise HTTPException(404, "Image not found")
    db.delete(image)
    db.flush()  # PG triggers atomically enqueue Mongo refresh and durable object deletion.
    remaining = db.query(ProductImage).filter_by(product_id=product_id).order_by(ProductImage.display_order).all()
    if remaining and not any(item.is_primary for item in remaining):
        remaining[0].is_primary = True
    db.commit()


@router.post("/{product_id}/reviews", response_model=ReviewResponse)
def create_product_review(
    product_id: int,
    review_in: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rating 0 is a violation report and lands in the moderator queue."""
    return crud_product.create_review(db, product_id, review_in, buyer_id=current_user.user_id)


# ---------- moderation ----------


@router.post("/{product_id}/approve", response_model=ProductResponse)
def approve_product(product_id: int, moderator: User = Depends(get_current_moderator), db: Session = Depends(get_db)):
    product = _get_or_404(db, product_id)
    if product.status != ProductStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sản phẩm không ở trạng thái chờ duyệt")
    return crud_product.moderate(db, product, ProductStatus.APPROVED, moderator.user_id)


@router.post("/{product_id}/reject", response_model=ProductResponse)
def reject_product(
    product_id: int,
    reject_reason: str = Query(..., min_length=10),
    moderator: User = Depends(get_current_moderator),
    db: Session = Depends(get_db),
):
    product = _get_or_404(db, product_id)
    if product.status != ProductStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sản phẩm không ở trạng thái chờ duyệt")
    return crud_product.moderate(db, product, ProductStatus.REJECTED, moderator.user_id, reject_reason)


@router.post("/{product_id}/status", response_model=ProductResponse)
def update_product_status(
    product_id: int,
    new_status: int = Body(..., ge=1, le=2),
    reject_reason: str | None = Body(None),
    moderator: User = Depends(get_current_moderator),
    db: Session = Depends(get_db),
):
    product = _get_or_404(db, product_id)
    return crud_product.moderate(db, product, new_status, moderator.user_id, reject_reason)
