from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_moderator, get_db
from app.core.constants import ProductStatus, RoleId
from app.core.exceptions import AppError
from app.crud.moderator import crud_moderator
from app.crud.product import crud_product
from app.models import User
from app.schemas import (
    Message,
    ProductApprovalRequest,
    ProductResponse,
    ReviewResponse,
    UserBanRequest,
    UserLockRequest,
    UserResponse,
    ViolationLogResponse,
)

router = APIRouter(prefix="/moderator", tags=["moderator"], dependencies=[Depends(get_current_moderator)])


@router.get("/products/pending", response_model=list[ProductResponse])
def get_pending_products(db: Session = Depends(get_db)):
    return crud_product.get_by_status(db, ProductStatus.PENDING, limit=1000)


@router.patch("/products/{product_id}/status", response_model=ProductResponse)
def change_product_status(
    product_id: int,
    approval: ProductApprovalRequest,
    db: Session = Depends(get_db),
    moderator: User = Depends(get_current_moderator),
):
    """0: pending, 1: approved, 2: rejected (reason required)."""
    product = crud_product.get_for_moderation(db, product_id)
    return crud_product.moderate(db, product, approval.status, moderator.user_id, approval.reason)


@router.get("/reviews/violations", response_model=list[ReviewResponse])
def get_violation_reviews(db: Session = Depends(get_db)):
    """Reviews submitted with rating 0, i.e. reports from buyers."""
    return crud_moderator.get_reported_reviews(db)


@router.post("/reviews/{review_id}/violation", response_model=Message)
def handle_violation_report(review_id: int, db: Session = Depends(get_db)):
    crud_moderator.handle_violation_report(db, review_id)
    return Message(message="Violation handled successfully")


@router.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db)):
    return crud_moderator.get_users_by_role(db, RoleId.USER)


@router.post("/users/{user_id}/ban", response_model=Message)
def ban_user(user_id: int, ban_request: UserBanRequest, db: Session = Depends(get_db)):
    crud_moderator.toggle_user_status(db, user_id, is_active=False, reason=ban_request.reason)
    return Message(message="User deactivated successfully")


@router.post("/users/{user_id}/unban", response_model=Message)
def unban_user(user_id: int, ban_request: UserBanRequest, db: Session = Depends(get_db)):
    crud_moderator.toggle_user_status(db, user_id, is_active=True, reason=ban_request.reason)
    return Message(message="User activated successfully")


@router.post("/users/{user_id}/lock-unlock")
def lock_unlock_user(user_id: int, lock_request: UserLockRequest, db: Session = Depends(get_db)):
    is_active = lock_request.action == "unlock"
    try:
        user = crud_moderator.toggle_user_status(db, user_id, is_active=is_active, reason=lock_request.reason)
    except AppError as exc:  # the UI expects 400 for every failure here, including "not found"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc
    return {
        "message": f"User {'unlocked' if is_active else 'locked'} successfully",
        "user": UserResponse.model_validate(user),
    }


@router.get("/violation-logs", response_model=list[ViolationLogResponse])
def get_violation_logs(user_id: int | None = None, db: Session = Depends(get_db)):
    return crud_moderator.get_violation_logs(db, user_id=user_id)
