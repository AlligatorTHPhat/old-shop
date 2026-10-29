import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import any_user, customer, get_current_moderator, get_current_user, get_current_user_optional, get_db
from app.core.constants import ProductStatus, RoleId
from app.crud.category import crud_category
from app.crud.product import crud_product
from app.models import Product, User
from app.schemas import (
    Message,
    ProductDetailResponse,
    ProductResponse,
    ProductUpdate,
    ReviewCreate,
    ReviewResponse,
    StatusUpdate,
)
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
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Approved products. Logged-in sellers don't see their own listings."""
    if search:
        products = crud_product.search(db, search, skip=skip, limit=limit)
    elif category_id:
        products = crud_product.get_by_category(db, category_id, skip=skip, limit=limit, order_by=sort_by)
    else:
        products = crud_product.get_approved(db, skip=skip, limit=limit, order_by=sort_by)

    if current_user:
        products = [p for p in products if p.seller_id != current_user.user_id]
    return products


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
    return product


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
    try:
        for index, file in enumerate(files, start=1):
            saved.append(await save_image(file, "products", f"prod_{product.product_id}_{index}"))
        await run_in_threadpool(crud_product.add_images, db, product, saved)
        db.commit()
    except Exception:
        db.rollback()
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
    product = _get_or_404(db, product_id)
    _ensure_owner_or_admin(product, current_user)

    new_category = product_update.category_id
    if new_category and new_category != product.category_id and not crud_category.get_by_id(db, new_category):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found")

    return crud_product.update(db, product, product_update)


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
