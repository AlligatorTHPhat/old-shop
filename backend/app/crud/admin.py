import logging

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import OrderStatus, ProductStatus, RoleId
from app.core.exceptions import BadRequestError
from app.core.security import hash_password
from app.crud.user import new_random_key
from app.models import Order, Product, Role, SystemFeedback, User
from app.schemas import AdminDashboardStats, SystemFeedbackCreate, UserCreate

logger = logging.getLogger(__name__)


class CRUDAdmin:
    def get_stats(self, db: Session) -> AdminDashboardStats:
        return AdminDashboardStats(
            total_users=db.query(func.count(User.user_id))
            .filter(User.is_active == True, User.is_deleted == False)
            .scalar(),
            total_orders=db.query(func.count(Order.order_id)).filter(Order.is_deleted == False).scalar(),
            pending_products=db.query(func.count(Product.product_id))
            .filter(Product.status == ProductStatus.PENDING, Product.is_deleted == False)
            .scalar(),
            total_revenue=db.query(func.sum(Order.final_amount))
            .filter(Order.order_status == OrderStatus.DELIVERED, Order.is_deleted == False)
            .scalar()
            or 0,
        )

    def list_users(self, db: Session, skip: int = 0, limit: int = 20) -> list[User]:
        return db.query(User).filter(User.is_deleted == False).offset(skip).limit(limit).all()

    def create_moderator(self, db: Session, data: UserCreate) -> User:
        role = db.get(Role, RoleId.MODERATOR)
        user = User(
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
            random_key=new_random_key(),
            full_name=data.full_name,
            phone_number=data.phone_number,
            address=data.address,
            is_active=True,
            is_deleted=False,
        )
        user.roles.append(role)
        db.add(user)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            # Map constraint errors to friendly messages without leaking the schema.
            error = str(exc.orig).lower()
            if "username" in error:
                raise BadRequestError("Tên đăng nhập đã tồn tại trong hệ thống.") from exc
            if "email" in error:
                raise BadRequestError("Email này đã được sử dụng.") from exc
            raise BadRequestError("Thông tin đăng ký không hợp lệ.") from exc
        db.refresh(user)
        logger.info("Moderator created", extra={"moderator_id": user.user_id})
        return user

    # ---------- feedback ----------

    def create_feedback(self, db: Session, feedback_in: SystemFeedbackCreate, user_id: int | None) -> SystemFeedback:
        feedback = SystemFeedback(**feedback_in.model_dump(), user_id=user_id)
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        return feedback

    def list_feedbacks(self, db: Session, skip: int = 0, limit: int = 100) -> list[SystemFeedback]:
        return db.query(SystemFeedback).order_by(SystemFeedback.created_at.desc()).offset(skip).limit(limit).all()

    def update_feedback_status(self, db: Session, feedback_id: int, status: int) -> SystemFeedback | None:
        feedback = db.get(SystemFeedback, feedback_id)
        if feedback:
            feedback.status = status
            db.commit()
            db.refresh(feedback)
        return feedback


crud_admin = CRUDAdmin()
