from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from app.core.constants import ProductStatus
from app.schemas.common import ORMModel
from app.schemas.user import UserResponse

# ---------- Category ----------


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    parent_id: int | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None


class CategoryResponse(CategoryBase, ORMModel):
    category_id: int
    is_active: bool
    is_deleted: bool
    created_at: datetime


# ---------- Product ----------


class ProductImageResponse(ORMModel):
    image_id: int
    image_url: str
    alt_text: str | None = None
    is_primary: bool = False
    display_order: int = 0


class ProductBase(BaseModel):
    category_id: int
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    price: Decimal = Field(..., gt=0)
    quantity: int = Field(..., ge=0)
    video_url: str | None = None
    weight_grams: int | None = None
    dimensions: str | None = None
    condition_rating: int | None = Field(None, ge=1, le=10)
    warranty_months: int = 0
    transfer_method: int = Field(1, ge=1, le=2)  # 1: shipping, 2: meetup


class ProductUpdate(BaseModel):
    category_id: int | None = None
    title: str | None = None
    description: str | None = None
    price: Decimal | None = None
    quantity: int | None = None
    video_url: str | None = None
    weight_grams: int | None = None
    dimensions: str | None = None
    condition_rating: int | None = None
    warranty_months: int | None = None
    transfer_method: int | None = None


class StatusUpdate(BaseModel):
    new_status: int
    reject_reason: str | None = None


class ProductResponse(ProductBase, ORMModel):
    product_id: int
    seller_id: int
    status: int
    reject_reason: str | None = None
    view_count: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime | None = None
    product_images: list[ProductImageResponse] = []

    @computed_field
    @property
    def is_approved(self) -> bool:
        return self.status == ProductStatus.APPROVED


# ---------- Review ----------


class ReviewCreate(BaseModel):
    product_id: int | None = None
    rating: int = Field(..., ge=0, le=5)  # 0 = report a violation
    title: str | None = Field(None, max_length=255)
    content: str | None = None


class ProductReviewResponse(ORMModel):
    """Review as embedded in a product page."""

    review_id: int
    product_id: int
    buyer_id: int
    rating: int
    content: str | None = None
    created_at: datetime
    reviewer: UserResponse | None = None


class ReviewResponse(ORMModel):
    """Full review, used by moderation endpoints."""

    review_id: int
    product_id: int | None = None
    buyer_id: int
    rating: int
    title: str | None = None
    content: str | None = None
    is_verified_purchase: bool
    helpful_count: int
    created_at: datetime
    updated_at: datetime | None = None
    is_deleted: bool
    reviewer: UserResponse | None = None
    product: ProductResponse | None = None


class ProductDetailResponse(ProductResponse):
    seller: UserResponse | None = None
    reviews: list[ProductReviewResponse] = []
