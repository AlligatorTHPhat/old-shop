from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.core.constants import RoleId
from app.crud.admin import crud_admin
from app.crud.moderator import crud_moderator
from app.models import User, Voucher
from app.schemas import (
    AdminDashboardStats,
    SystemFeedbackResponse,
    UserCreate,
    UserLockRequest,
    UserResponse,
    ViolationLogResponse,
    VoucherCreate,
    VoucherResponse,
    VoucherUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminDashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    sales_year: int | None = Query(None, ge=2000, le=2100),
):
    return crud_admin.get_stats(db, sales_year)


@router.get("/users", response_model=list[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return crud_admin.list_users(db, skip=skip, limit=limit)


# ---------- feedback ----------


@router.get("/feedbacks", response_model=list[SystemFeedbackResponse])
def list_feedbacks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return crud_admin.list_feedbacks(db, skip=skip, limit=limit)


@router.patch("/feedbacks/{feedback_id}", response_model=SystemFeedbackResponse)
def update_feedback(
    feedback_id: int,
    status_update: int = Query(..., ge=0, le=2),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    feedback = crud_admin.update_feedback_status(db, feedback_id, status_update)
    if not feedback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    return feedback


# ---------- moderators ----------


@router.get("/moderators", response_model=list[UserResponse])
def list_moderators(
    include_deleted: bool = Query(False), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)
):
    return crud_moderator.get_users_by_role(db, RoleId.MODERATOR, include_deleted=include_deleted)


@router.post("/moderators", response_model=UserResponse)
def create_moderator(moderator_in: UserCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    return crud_admin.create_moderator(db, moderator_in)


@router.patch("/moderators/{user_id}/status", response_model=UserResponse)
def toggle_moderator_status(
    user_id: int,
    status_update: UserLockRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return crud_moderator.toggle_moderator_status(
        db, user_id, is_active=status_update.action == "unlock", reason=status_update.reason
    )


@router.get("/violation-logs", response_model=list[ViolationLogResponse])
def get_violation_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return crud_moderator.get_violation_logs(db, skip=skip, limit=limit)


# ---------- vouchers ----------


def _get_voucher(db: Session, voucher_id: int) -> Voucher:
    voucher = db.get(Voucher, voucher_id)
    if not voucher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voucher không tồn tại.")
    return voucher


@router.get("/vouchers", response_model=list[VoucherResponse])
def list_all_vouchers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """All vouchers, including expired and soft-deleted ones."""
    return db.query(Voucher).order_by(Voucher.voucher_id).offset(skip).limit(limit).all()


@router.post("/vouchers", response_model=VoucherResponse)
def create_voucher(voucher_in: VoucherCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    code = voucher_in.code.strip().upper()
    if db.query(Voucher).filter(Voucher.code == code).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mã voucher này đã tồn tại.")
    voucher = Voucher(**voucher_in.model_dump(exclude={"code"}), code=code)
    db.add(voucher)
    db.commit()
    db.refresh(voucher)
    return voucher


@router.patch("/vouchers/{voucher_id}", response_model=VoucherResponse)
def update_voucher(
    voucher_id: int,
    voucher_update: VoucherUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    voucher = _get_voucher(db, voucher_id)
    for key, value in voucher_update.model_dump(exclude_unset=True).items():
        setattr(voucher, key, value)
    db.commit()
    db.refresh(voucher)
    return voucher


@router.delete("/vouchers/{voucher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voucher(voucher_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    voucher = _get_voucher(db, voucher_id)
    voucher.is_deleted = True
    voucher.is_active = False
    db.commit()


@router.delete("/vouchers/{voucher_id}/hard-delete", status_code=status.HTTP_204_NO_CONTENT)
def hard_delete_voucher(voucher_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    db.delete(_get_voucher(db, voucher_id))
    db.commit()
