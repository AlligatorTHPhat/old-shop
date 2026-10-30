"""Day 3 document contracts. PG remains authoritative for transactional fields."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

Identifier = Annotated[int, Field(gt=0, le=9223372036854775807)]
VND = Annotated[int, Field(ge=0, le=9223372036854775807)]


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True, allow_inf_nan=False)


class Document(DocumentModel):
    id: str = Field(alias="_id", min_length=1, max_length=200)
    schema_version: Literal[1] = 1
    deleted: bool = False


class ObjectReference(DocumentModel):
    bucket: str = Field(min_length=3, max_length=63)
    key: str = Field(min_length=1, max_length=1024)
    content_type: str | None = None
    size: Annotated[int, Field(ge=0)] | None = None


class ProductImageReference(ObjectReference):
    image_id: Identifier | None = None
    is_primary: bool = False
    display_order: int = 0


class Dimensions(DocumentModel):
    length: float = Field(gt=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["cm", "mm", "m"] = "cm"


class Condition(DocumentModel):
    grade: int = Field(ge=1, le=10)
    warranty_months: int = Field(default=0, ge=0)
    defects: list[str] = Field(default_factory=list)


class ETLMetadata(DocumentModel):
    synced_at: AwareDatetime
    source_updated_at: AwareDatetime | None = None
    run_id: str | None = None
    source_created_at: str | None = None


class ProductDetails(Document):
    product_id: Identifier
    category_id: Identifier
    description: str | None = None
    video_url: str | None = None
    weight_grams: Annotated[int, Field(ge=0)] | None = None
    dimensions: Dimensions | None = None
    dimensions_raw: str | None = None
    condition: Condition | None = None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    images: list[ProductImageReference] = Field(default_factory=list)
    updated_at: AwareDatetime
    deleted: bool = False
    etl: ETLMetadata | None = None


class Moderation(DocumentModel):
    actor_id: Identifier
    at: AwareDatetime
    reason: str | None = None


class ReviewDocument(Document):
    review_id: Identifier
    product_id: Identifier
    buyer_id: Identifier
    type: Literal["review", "report"]
    rating: int = Field(ge=0, le=5)
    title: str | None = None
    content: str | None = None
    status: Literal["pending", "approved", "rejected"] | None = None
    moderation: Moderation | None = None
    evidence: list[ObjectReference] = Field(default_factory=list)
    created_at: AwareDatetime
    updated_at: AwareDatetime | None = None
    deleted: bool = False
    etl: ETLMetadata | None = None

    @model_validator(mode="after")
    def report_rating(self) -> Self:
        if (self.type == "report") != (self.rating == 0):
            raise ValueError("rating=0 must be a report; a review must have rating 1..5")
        return self


class BuyerReference(DocumentModel):
    id: Identifier
    region: Literal["north", "central", "south", "unknown"] | None = None


class OrderSnapshotItem(DocumentModel):
    product_id: Identifier
    quantity: int = Field(gt=0)
    price_at_purchase_vnd: VND
    subtotal_vnd: VND
    title_current: str | None = None
    category_id_current: Identifier | None = None
    seller_id_current: Identifier | None = None


class PaymentSnapshot(DocumentModel):
    transaction_id: Identifier
    method_id: Identifier
    status_code: int  # Preserve raw source code until D8; no invented status mapping.
    amount_vnd: VND
    fraud_score: Annotated[float, Field(ge=0, le=1)] | None = None


class VoucherSnapshot(DocumentModel):
    voucher_id: Identifier
    discount_type_code_current: int
    discount_value_current: str = Field(pattern=r"^\d+(\.\d+)?$")
    is_active_current: bool
    is_deleted_current: bool


class OrderSnapshot(Document):
    order_id: Identifier
    buyer: BuyerReference
    items: list[OrderSnapshotItem] = Field(min_length=1)
    payments: list[PaymentSnapshot] = Field(default_factory=list)
    total_amount_vnd: VND
    shipping_fee_vnd: VND
    discount_amount_vnd: VND
    final_amount_vnd: VND
    voucher_id: Identifier | None = None
    voucher_current: VoucherSnapshot | None = None
    order_status: int = Field(ge=0, le=4)
    order_date: AwareDatetime
    deleted: bool = False
    etl: ETLMetadata


class LogPayload(DocumentModel):
    event: str | None = None
    reason_code: str | None = None
    changed_fields: list[str] = Field(default_factory=list)


class SystemLogDocument(Document):
    log_id: Identifier
    actor_id: Identifier | None = None
    action: str = Field(min_length=1, max_length=100)
    resource_type: str | None = None
    resource_id: int | None = None
    message: str | None = Field(default=None, max_length=2000)
    payload: LogPayload | None = None
    ip_hash: str | None = None
    created_at: AwareDatetime
    etl: ETLMetadata | None = None


class ViolationLogDocument(Document):
    log_id: Identifier
    target_user_id: Identifier
    actor_id: Identifier | None = None  # PG source does not contain this field.
    reason: str = Field(min_length=1, max_length=500)
    action_taken: str = Field(min_length=1, max_length=100)
    created_at: AwareDatetime
    payload: LogPayload | None = None
    etl: ETLMetadata | None = None


class ContactMessageDocument(Document):
    feedback_id: Identifier
    user_id: Identifier | None = None
    subject: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    status: int = Field(ge=0, le=2)
    attachments: list[ObjectReference] = Field(default_factory=list)
    created_at: AwareDatetime
    etl: ETLMetadata | None = None


DOCUMENT_MODELS = {
    "product_details": ProductDetails,
    "reviews": ReviewDocument,
    "order_snapshots": OrderSnapshot,
    "system_logs": SystemLogDocument,
    "violation_logs": ViolationLogDocument,
    "contact_messages": ContactMessageDocument,
}
