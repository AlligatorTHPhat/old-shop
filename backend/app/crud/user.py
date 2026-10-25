import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.core.constants import RoleId
from app.core.security import hash_password, verify_password
from app.crud.base import CRUDBase
from app.models import ContactInfo, ShoppingCart, User, UserRole
from app.schemas import UserCreate

RESET_TOKEN_TTL = timedelta(minutes=30)
OTP_TTL = timedelta(minutes=5)


def new_random_key() -> str:
    return secrets.token_hex(32)


class CRUDUser(CRUDBase[User]):
    def get_by_username(self, db: Session, username: str) -> User | None:
        return db.query(User).filter(User.username == username).first()

    def get_by_email(self, db: Session, email: str) -> User | None:
        return db.query(User).filter(User.email == email).first()

    def get_with_roles_by_email(self, db: Session, email: str) -> User | None:
        return db.query(User).options(joinedload(User.roles)).filter(User.email == email).first()

    def generate_username(self, db: Session, email: str) -> str:
        base = email.split("@")[0][:40]
        while True:
            candidate = f"{base}_{secrets.token_hex(2)}"
            if not self.get_by_username(db, candidate):
                return candidate

    def register(self, db: Session, obj_in: UserCreate) -> User:
        """Create a user with its role, a default address book entry and an empty cart."""
        role_id = obj_in.role_id or RoleId.USER
        user = User(
            username=obj_in.username,
            email=obj_in.email,
            password_hash=hash_password(obj_in.password),
            full_name=obj_in.full_name,
            phone_number=obj_in.phone_number,
            address=obj_in.address,
            avatar_url=f"/media/users/user_{role_id}_{obj_in.username}.png",
            random_key=new_random_key(),
        )
        db.add(user)
        db.flush()  # assigns user_id

        db.add(UserRole(user_id=user.user_id, role_id=role_id))
        db.add(
            ContactInfo(
                user_id=user.user_id,
                full_name=obj_in.full_name,
                phone_number=obj_in.phone_number,
                address=obj_in.address,
                is_default=True,
            )
        )
        db.add(ShoppingCart(user_id=user.user_id))
        db.commit()
        db.refresh(user)
        return user

    def get_active_with_roles(self, db: Session, skip: int = 0, limit: int = 100) -> list[User]:
        return (
            db.query(User)
            .options(joinedload(User.roles))
            .filter(User.is_deleted == False, User.is_active == True)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def touch_last_login(self, db: Session, user: User) -> None:
        user.last_login = datetime.utcnow()
        db.commit()

    def change_password(self, db: Session, user: User, current_password: str, new_password: str) -> bool:
        if not verify_password(current_password, user.password_hash):
            return False
        user.password_hash = hash_password(new_password)
        db.commit()
        return True

    # Password reset: a long token (link flow) or a 6-digit OTP (email flow) share the same columns.

    def _issue_reset_secret(self, db: Session, email: str, secret: str, ttl: timedelta) -> str | None:
        user = self.get_by_email(db, email)
        if not user:
            return None
        user.password_reset_token = secret
        user.password_reset_expires = datetime.utcnow() + ttl
        db.commit()
        return secret

    def request_password_reset(self, db: Session, email: str) -> str | None:
        return self._issue_reset_secret(db, email, secrets.token_urlsafe(32), RESET_TOKEN_TTL)

    def request_otp_reset(self, db: Session, email: str) -> str | None:
        return self._issue_reset_secret(db, email, f"{secrets.randbelow(900000) + 100000}", OTP_TTL)

    def _consume_reset_secret(self, db: Session, user: User | None, new_password: str) -> bool:
        if not user or not user.password_reset_expires or user.password_reset_expires < datetime.utcnow():
            return False
        user.password_hash = hash_password(new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        db.commit()
        return True

    def reset_password(self, db: Session, token: str, new_password: str) -> bool:
        user = db.query(User).filter(User.password_reset_token == token).first()
        return self._consume_reset_secret(db, user, new_password)

    def verify_otp_and_reset(self, db: Session, email: str, otp: str, new_password: str) -> bool:
        user = self.get_by_email(db, email)
        if user is None or not user.password_reset_token or not secrets.compare_digest(user.password_reset_token, otp):
            return False
        return self._consume_reset_secret(db, user, new_password)


crud_user = CRUDUser(User)
