from datetime import datetime

from sqlalchemy import DECIMAL, Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from app.core.constants import RoleId
from app.core.database import Base


class Role(Base):
    __tablename__ = "role"

    role_id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(255))
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    users = relationship("User", secondary="user_role", back_populates="roles")

    __table_args__ = (
        Index("idx_role_name", "role_name", postgresql_where=(is_deleted.is_(False))),
        Index("idx_role_created_at", "created_at"),
    )


class User(Base):
    __tablename__ = "user_core"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    email_verified = Column(Boolean, default=False, nullable=False)
    trust_score = Column(DECIMAL(5, 2), default=0.0, nullable=True)

    _profile = relationship("UserProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")
    _secret = relationship("UserSecret", uselist=False, back_populates="user", cascade="all, delete-orphan")
    _wallet = relationship("UserWallet", uselist=False, back_populates="user", cascade="all, delete-orphan")
    full_name = association_proxy("_profile", "full_name")
    phone_number = association_proxy("_profile", "phone_number")
    address = association_proxy("_profile", "address")
    avatar_url = association_proxy("_profile", "avatar_url")
    password_hash = association_proxy("_secret", "password_hash")
    random_key = association_proxy("_secret", "random_key")
    email_verification_token = association_proxy("_secret", "email_verification_token")
    password_reset_token = association_proxy("_secret", "password_reset_token")
    password_reset_expires = association_proxy("_secret", "password_reset_expires")
    balance = association_proxy("_wallet", "balance")

    def __init__(self, **kwargs):
        # The unit of work inserts all fragments in the SAME transaction, including admins.
        super().__init__(_profile=UserProfile(), _secret=UserSecret(), _wallet=UserWallet())
        for key, value in kwargs.items():
            if not hasattr(type(self), key):
                raise TypeError(f"Invalid User field: {key}")
            setattr(self, key, value)

    roles = relationship("Role", secondary="user_role", back_populates="users")
    # Association rows, for code that needs the join object itself; `roles` is the usual accessor.
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan", overlaps="roles,users")
    products = relationship("Product", foreign_keys="Product.seller_id", back_populates="seller")
    approved_products = relationship("Product", foreign_keys="Product.approved_by", back_populates="approved_by_user")
    orders = relationship("Order", back_populates="buyer")
    contact_info = relationship("ContactInfo", back_populates="user", cascade="all, delete-orphan")
    shopping_cart = relationship("ShoppingCart", back_populates="user", uselist=False, cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="reviewer")
    transactions = relationship("Transaction", back_populates="user")
    feedbacks = relationship("SystemFeedback", back_populates="user")

    __table_args__ = (
        Index("idx_user_username_active", "username", postgresql_where=(is_deleted.is_(False))),
        Index("idx_user_email_active", "email", postgresql_where=(is_deleted.is_(False))),
        Index("idx_user_created_at", "created_at"),
        Index("idx_user_is_active", "is_active", postgresql_where=(is_deleted.is_(False))),
        Index("idx_user_email_verified", "email_verified", postgresql_where=(is_deleted.is_(False))),
    )

    @property
    def role_ids(self) -> list[int]:
        return [role.role_id for role in self.roles]

    @property
    def role_id(self) -> int:
        """Primary role. A user has exactly one role in practice; default to USER."""
        return self.roles[0].role_id if self.roles else RoleId.USER

    def has_role(self, *roles: int) -> bool:
        return any(role_id in roles for role_id in self.role_ids)


class UserProfile(Base):
    __tablename__ = "user_profile"
    user_id = Column(Integer, ForeignKey("user_core.user_id", ondelete="CASCADE"), primary_key=True)
    full_name = Column(String(100), nullable=False)
    phone_number = Column(String(15))
    address = Column(String(255))
    avatar_url = Column(String(500))
    user = relationship("User", back_populates="_profile")


class UserSecret(Base):
    __tablename__ = "user_secret"
    user_id = Column(Integer, ForeignKey("user_core.user_id", ondelete="CASCADE"), primary_key=True)
    password_hash = Column(String(255), nullable=False)
    random_key = Column(String(64), unique=True, nullable=False)
    email_verification_token = Column(String(255))
    password_reset_token = Column(String(255))
    password_reset_expires = Column(DateTime)
    user = relationship("User", back_populates="_secret")


class UserWallet(Base):
    __tablename__ = "user_wallet"
    user_id = Column(Integer, ForeignKey("user_core.user_id", ondelete="CASCADE"), primary_key=True)
    balance = Column(DECIMAL(18, 4), default=10000000, nullable=False)
    user = relationship("User", back_populates="_wallet")


class UserRole(Base):
    __tablename__ = "user_role"

    user_id = Column(Integer, ForeignKey("user_core.user_id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("role.role_id"), primary_key=True)

    user = relationship("User", back_populates="user_roles", overlaps="roles,users")
    role = relationship("Role", overlaps="roles,users")


# Match the original User.updated_at behavior when a profile/secret/wallet changes.
# SQLAlchemy events run inside the same transaction, without writing the join view.
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@event.listens_for(Session, "before_flush")
def _touch_user_fragments(session, flush_context, instances):
    for fragment in list(session.dirty):
        if isinstance(fragment, (UserProfile, UserSecret, UserWallet)) and session.is_modified(fragment):
            fragment.user.updated_at = datetime.utcnow()
