from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.catalog import ProductResponse
from app.schemas.common import ORMModel
from app.schemas.user import UserResponse

# ---------- Payment method / address book ----------


class PaymentMethodResponse(ORMModel):
    payment_method_id: int
    method_name: str
    is_online: bool
    is_deleted: bool


class ContactInfoBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str = Field(..., max_length=15)
    address: str = Field(..., max_length=255)
    province: str | None = None
    district: str | None = None
    ward: str | None = None


class ContactInfoCreate(ContactInfoBase):
    is_default: bool = False


class ContactInfoResponse(ContactInfoBase, ORMModel):
    contact_id: int
    user_id: int
    is_default: bool
    is_deleted: bool
    created_at: datetime


# ---------- Order ----------


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)


class OrderBase(BaseModel):
    contact_id: int
    payment_method_id: int
    voucher_code: str | None = None
    shipping_fee: Decimal = Field(default=Decimal("0"), ge=0)
    shipping_address: str | None = None
    phone_number: str | None = None
    notes: str | None = None


class OrderCreate(OrderBase):
    order_items: list[OrderItemCreate]

    @field_validator("order_items")
    @classmethod
    def _not_empty(cls, items: list[OrderItemCreate]) -> list[OrderItemCreate]:
        if not items:
            raise ValueError("Order must have at least one item")
        return items


class OrderUpdate(BaseModel):
    order_status: int | None = None
    tracking_number: str | None = None
    notes: str | None = None


class OrderDetailResponse(ORMModel):
    order_detail_id: int
    product_id: int
    quantity: int
    price_at_purchase: Decimal
    subtotal: Decimal
    product: ProductResponse | None = None


class OrderResponse(OrderBase, ORMModel):
    order_id: int
    buyer_id: int
    order_date: datetime
    total_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    order_status: int
    tracking_number: str | None = None
    is_deleted: bool


class OrderWithDetailsResponse(OrderResponse):
    order_details: list[OrderDetailResponse] = []
    buyer: UserResponse | None = None


# ---------- Voucher ----------


class VoucherBase(BaseModel):
    code: str = Field(..., max_length=50)
    description: str | None = None
    discount_type: int = 0  # see DiscountType
    discount_value: Decimal = Field(..., gt=0)
    max_usage: int | None = None
    min_order_amount: Decimal | None = None
    valid_from: datetime
    valid_to: datetime


class VoucherCreate(VoucherBase):
    pass


class VoucherUpdate(BaseModel):
    description: str | None = None
    discount_value: Decimal | None = None
    max_usage: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    min_order_amount: Decimal | None = None
    is_active: bool | None = None
    is_deleted: bool | None = None


class VoucherResponse(VoucherBase, ORMModel):
    voucher_id: int
    usage_count: int
    is_active: bool
    is_deleted: bool
    created_at: datetime


class VoucherCheckResponse(BaseModel):
    voucher_id: int
    code: str
    discount_type: int
    discount_value: float
    calculated_discount: float
    description: str | None = None
