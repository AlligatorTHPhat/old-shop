from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class ProductApprovalRequest(BaseModel):
    product_id: int | None = None
    status: int = Field(..., ge=0, le=2)  # 0: pending, 1: approved, 2: rejected
    reason: str | None = Field(None, max_length=500)


class UserBanRequest(BaseModel):
    user_id: int | None = None
    reason: str = Field(..., max_length=500)


class UserLockRequest(BaseModel):
    action: str = Field(..., pattern="^(lock|unlock)$")
    reason: str = Field(..., max_length=500)


class ViolationLogResponse(ORMModel):
    log_id: int
    user_id: int
    username: str | None = None
    reason: str
    action_taken: str
    created_at: datetime


class SystemFeedbackCreate(BaseModel):
    guest_email: EmailStr | None = None
    subject: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)


class ContactMessageCreate(BaseModel):
    """Public contact form. Stored as feedback and relayed to Google Apps Script."""

    full_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(None, max_length=20)
    subject: str | None = Field(None, max_length=200)
    message: str = Field(..., min_length=1, max_length=5000)


class SystemFeedbackResponse(ORMModel):
    feedback_id: int
    user_id: int | None = None
    guest_email: str | None = None
    subject: str
    content: str
    status: int
    created_at: datetime


class AdminDashboardStats(BaseModel):
    total_users: int
    total_revenue: Decimal
    pending_products: int
    total_orders: int
