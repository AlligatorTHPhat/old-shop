from sqlalchemy.orm import Session, joinedload

from app.core.constants import REPORT_RATING, ProductStatus, RoleId
from app.core.exceptions import BadRequestError, NotFoundError
from app.models import Review, User, UserRole, ViolationLog

TRUST_PENALTY = 10.0


class CRUDModerator:
    def get_users_by_role(self, db: Session, role_id: int, include_deleted: bool = False) -> list[User]:
        query = db.query(User).join(UserRole).filter(UserRole.role_id == role_id)
        if not include_deleted:
            query = query.filter(User.is_deleted == False)
        return query.distinct().all()

    def get_reported_reviews(self, db: Session) -> list[Review]:
        return db.query(Review).filter(Review.rating == REPORT_RATING, Review.is_deleted == False).all()

    def get_violation_logs(self, db: Session, user_id: int | None = None, skip: int = 0, limit: int = 100):
        """Logs joined with the username of the sanctioned account."""
        query = (
            db.query(
                ViolationLog.log_id,
                ViolationLog.user_id,
                ViolationLog.reason,
                ViolationLog.action_taken,
                ViolationLog.created_at,
                User.username.label("username"),
            )
            .join(User, ViolationLog.user_id == User.user_id)
            .order_by(ViolationLog.created_at.desc())
        )
        if user_id is not None:
            query = query.filter(ViolationLog.user_id == user_id)
        return query.offset(skip).limit(limit).all()

    def handle_violation_report(self, db: Session, review_id: int) -> Review:
        """Take the reported product down and penalise the seller's trust score (ban at 0)."""
        review = db.query(Review).filter(Review.review_id == review_id, Review.is_deleted == False).first()
        if not review:
            raise NotFoundError("Review not found")

        product, seller = review.product, review.product.seller
        product.status = ProductStatus.REJECTED
        product.reject_reason = f"Violation reported on review {review_id}"

        reason = f"Violation on review {review_id} for product {product.product_id}"
        if seller.has_role(RoleId.USER):
            seller.trust_score = max(0.0, float(seller.trust_score or 0) - TRUST_PENALTY)
            db.add(ViolationLog(user_id=seller.user_id, reason=reason, action_taken="PRODUCT_REMOVAL"))
            if seller.trust_score <= 0:
                seller.is_active = False
                db.add(ViolationLog(user_id=seller.user_id, reason="Trust score dropped to 0", action_taken="BAN"))
        else:
            db.add(
                ViolationLog(
                    user_id=seller.user_id,
                    reason=f"{reason} (no trust score penalty - not a seller)",
                    action_taken="PRODUCT_REMOVAL",
                )
            )

        db.commit()
        db.refresh(review)
        return review

    def _set_active(
        self, db: Session, user_id: int, is_active: bool, reason: str, required_role: RoleId, log_suffix: str = ""
    ) -> User:
        user = db.query(User).options(joinedload(User.roles)).filter(User.user_id == user_id).first()
        if not user:
            raise NotFoundError("User not found")
        if not user.has_role(required_role):
            raise BadRequestError(f"Can only change status for users with role_id={int(required_role)}")
        if user.is_active == is_active:
            raise BadRequestError(f"Account is already {'active' if is_active else 'inactive'}")

        user.is_active = is_active
        action = ("ACTIVATE" if is_active else "DEACTIVATE") + log_suffix
        db.add(ViolationLog(user_id=user_id, reason=reason, action_taken=action))
        return user

    def toggle_user_status(self, db: Session, user_id: int, is_active: bool, reason: str) -> User:
        user = self._set_active(db, user_id, is_active, reason, RoleId.USER)
        db.commit()
        db.refresh(user)
        return user

    def toggle_moderator_status(self, db: Session, user_id: int, is_active: bool, reason: str) -> User:
        user = self._set_active(db, user_id, is_active, reason, RoleId.MODERATOR, log_suffix="_MODERATOR")
        # A locked moderator is also hidden from the moderator list.
        user.is_deleted = not is_active
        db.commit()
        db.refresh(user)
        return user


crud_moderator = CRUDModerator()
