from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_admin, get_current_user, get_db
from app.core.constants import OrderStatus, RoleId
from app.crud.user import crud_user
from app.models import ContactInfo, Order, OrderDetail, Product, Review, User
from app.schemas import (
    ChangePasswordRequest,
    ContactInfoCreate,
    ContactInfoResponse,
    Message,
    UserDetailResponse,
    UserResponse,
    UserUpdate,
)
from app.services.storage import delete_media, save_image

router = APIRouter(prefix="/users", tags=["users"])


def to_public_user(user: User) -> UserResponse:
    """Trust score is only meaningful (and shown) for seller accounts."""
    response = UserResponse.model_validate(user)
    if not user.has_role(RoleId.USER):
        response.trust_score = None
    return response


# ---------- current user ----------


@router.get("/me", response_model=UserDetailResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return to_public_user(current_user)


@router.put("/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Users cannot (re)activate themselves through their profile.
    return crud_user.update(db, current_user, user_update.model_dump(exclude_unset=True, exclude={"is_active"}))


@router.post("/me/change-password", response_model=Message)
def change_my_password(
    payload: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not crud_user.change_password(db, current_user, payload.current_password, payload.new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    return Message(message="Password updated successfully")


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Save an immutable image, then commit its URL; retain the old avatar until commit succeeds."""
    saved = await save_image(file, "users", f"user_{current_user.role_id}_{current_user.user_id}")
    try:
        current_user.avatar_url = saved
        db.commit()
    except Exception:
        db.rollback()
        await run_in_threadpool(delete_media, saved)
        raise
    db.refresh(current_user)
    return current_user


# ---------- address book ----------


@router.get("/me/contacts", response_model=list[ContactInfoResponse])
def get_my_contacts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(ContactInfo)
        .filter(ContactInfo.user_id == current_user.user_id, ContactInfo.is_deleted == False)
        .order_by(ContactInfo.is_default.desc(), ContactInfo.created_at.desc())
        .all()
    )


def _unset_default_contacts(db: Session, user_id: int) -> None:
    db.query(ContactInfo).filter(ContactInfo.user_id == user_id).update({"is_default": False})


def _get_own_contact(db: Session, user_id: int, contact_id: int) -> ContactInfo:
    contact = (
        db.query(ContactInfo)
        .filter(ContactInfo.contact_id == contact_id, ContactInfo.user_id == user_id, ContactInfo.is_deleted == False)
        .first()
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.post("/me/contacts", response_model=ContactInfoResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    contact_in: ContactInfoCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    has_contacts = (
        db.query(ContactInfo.contact_id)
        .filter(ContactInfo.user_id == current_user.user_id, ContactInfo.is_deleted == False)
        .first()
    )
    is_default = contact_in.is_default or not has_contacts  # the first address becomes the default
    if is_default:
        _unset_default_contacts(db, current_user.user_id)

    contact = ContactInfo(**contact_in.model_dump(exclude={"is_default"}), user_id=current_user.user_id)
    contact.is_default = is_default
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.post("/me/contacts/{contact_id}/set-default", response_model=ContactInfoResponse)
def set_default_contact(contact_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contact = _get_own_contact(db, current_user.user_id, contact_id)
    _unset_default_contacts(db, current_user.user_id)
    contact.is_default = True
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/me/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contact = _get_own_contact(db, current_user.user_id, contact_id)
    contact.is_deleted = True
    db.commit()


# ---------- seller dashboard ----------


@router.get("/seller/dashboard-stats")
def get_seller_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    seller_orders = db.query(Order).join(OrderDetail).join(Product).filter(Product.seller_id == current_user.user_id)

    total_products = (
        db.query(func.count(Product.product_id))
        .filter(Product.seller_id == current_user.user_id, Product.is_deleted == False)
        .scalar()
    )
    new_orders = seller_orders.filter(Order.order_status == OrderStatus.PENDING).count()
    revenue = (
        db.query(func.sum(Order.final_amount))
        .join(OrderDetail)
        .join(Product)
        .filter(Product.seller_id == current_user.user_id, Order.order_status == OrderStatus.DELIVERED)
        .scalar()
    )
    avg_rating = (
        db.query(func.avg(Review.rating)).join(Product).filter(Product.seller_id == current_user.user_id).scalar()
    )
    return {
        "totalProducts": total_products,
        "newOrders": new_orders,
        "revenue": float(revenue or 0),
        "rating": round(float(avg_rating or 0), 1),
    }


# ---------- admin / public profiles ----------


@router.get("", response_model=list[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return [to_public_user(u) for u in crud_user.get_active_with_roles(db, skip=skip, limit=limit)]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Public seller profile."""
    user = crud_user.get(db, user_id)
    if not user or user.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return to_public_user(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = crud_user.get(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    crud_user.soft_delete(db, user)
