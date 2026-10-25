import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.constants import RoleId
from app.core.security import create_access_token, verify_password
from app.crud.user import crud_user
from app.models import User
from app.schemas import (
    ForgotPasswordRequest,
    Message,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserDetailResponse,
    UserResponse,
    VerifyOTPRequest,
)
from app.services.mail import send_otp_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Same answer whether or not the email exists, to avoid account enumeration.
RESET_SENT = "Nếu email tồn tại, mã xác thực đã được gửi."


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Public sign-up. Always creates a customer (role 3); staff accounts are created by admins."""
    if user_in.role_id not in (None, RoleId.USER):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Role ID can only be 3 (User) for public registration.",
        )
    user_in.role_id = RoleId.USER
    user_in.username = user_in.username or crud_user.generate_username(db, user_in.email)

    if crud_user.get_by_username(db, user_in.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    if crud_user.get_by_email(db, user_in.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = crud_user.register(db, user_in)
    logger.info("User registered", extra={"user_id": user.user_id})
    return user


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow. The form field is called `username` but carries the email."""
    user = crud_user.get_with_roles_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        logger.info("Login failed", extra={"reason": "bad_credentials"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.is_deleted or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive")

    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        {"user_id": user.user_id, "username": user.email, "role_id": user.role_id}, expires_delta=expires
    )
    crud_user.touch_last_login(db, user)
    logger.info("Login succeeded", extra={"user_id": user.user_id})
    return TokenResponse(access_token=token, expires_in=int(expires.total_seconds()))


@router.get("/me", response_model=UserDetailResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password", response_model=Message)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Link-based reset is not wired to email yet; the OTP flow below is the one used by the UI.
    crud_user.request_password_reset(db, request.email)
    return Message(message=RESET_SENT)


@router.post("/reset-password", response_model=Message)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    if not crud_user.reset_password(db, request.token, request.new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token không hợp lệ hoặc đã hết hạn")
    return Message(message="Mật khẩu đã được cập nhật thành công")


@router.post("/forgot-password-otp", response_model=Message)
def forgot_password_otp(email: str, db: Session = Depends(get_db)):
    otp = crud_user.request_otp_reset(db, email)
    if otp and not send_otp_email(email, otp):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Lỗi hệ thống khi gửi email")
    return Message(message=RESET_SENT)


@router.post("/verify-reset-password", response_model=Message)
def verify_reset_password(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    if not crud_user.verify_otp_and_reset(db, request.email, request.otp, request.new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã OTP sai hoặc đã hết hạn")
    return Message(message="Mật khẩu đã được cập nhật thành công.")
