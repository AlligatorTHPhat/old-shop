from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RoleResponse(ORMModel):
    role_id: int
    role_name: str
    description: str | None = None
    is_deleted: bool
    created_at: datetime


class UserBase(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str | None = Field(None, max_length=15)
    address: str | None = Field(None, max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    role_id: int | None = 3


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone_number: str | None = None
    address: str | None = None
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)


class UserResponse(UserBase, ORMModel):
    user_id: int
    role_id: int | None = None
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime | None = None
    last_login: datetime | None = None
    email_verified: bool
    trust_score: float | None = None
    avatar_url: str | None = None
    balance: Decimal | None = None
    roles: list[RoleResponse] = []


# Kept as a separate name because the frontend contract distinguishes "me" from public profiles.
UserDetailResponse = UserResponse
