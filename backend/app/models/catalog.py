from datetime import datetime

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Category(Base):
    __tablename__ = "category"

    category_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey("category.category_id"))
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    products = relationship("Product", back_populates="category")
    parent = relationship("Category", remote_side=[category_id], backref="children")

    __table_args__ = (
        Index("idx_category_name_active", "name", postgresql_where=(is_deleted.is_(False))),
        Index("idx_category_parent", "parent_id", postgresql_where=(is_deleted.is_(False))),
        Index("idx_category_is_active", "is_active", postgresql_where=(is_deleted.is_(False))),
        Index("idx_category_created_at", "created_at"),
    )


class Product(Base):
    __tablename__ = "product"

    product_id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("user_core.user_id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("category.category_id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(DECIMAL(18, 2), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    view_count = Column(Integer, default=0)
    video_url = Column(String(500))
    status = Column(SmallInteger, default=0, nullable=False, index=True)  # see ProductStatus
    reject_reason = Column(String(500))
    approved_by = Column(Integer, ForeignKey("user_core.user_id"))
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    sold_at = Column(DateTime)
    weight_grams = Column(Integer)
    dimensions = Column(String(50))  # e.g. "10x20x5 cm"
    condition_rating = Column(SmallInteger)  # 1-10
    warranty_months = Column(Integer, default=0)
    transfer_method = Column(SmallInteger, default=1, nullable=True)  # 1: shipping, 2: meetup

    seller = relationship("User", foreign_keys=[seller_id], back_populates="products")
    approved_by_user = relationship("User", foreign_keys=[approved_by], back_populates="approved_products")
    category = relationship("Category", back_populates="products")
    product_images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    order_details = relationship("OrderDetail", back_populates="product")
    cart_items = relationship("ShoppingCartItem", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("price >= 0", name="check_product_price"),
        CheckConstraint("quantity >= 0", name="check_product_quantity"),
        CheckConstraint("status IN (0, 1, 2, 3)", name="check_product_status"),
        CheckConstraint("condition_rating BETWEEN 1 AND 10", name="check_condition_rating"),
        CheckConstraint("transfer_method IN (1, 2)", name="check_transfer_method"),
        Index("idx_product_seller", "seller_id", postgresql_where=(is_deleted.is_(False))),
        Index("idx_product_category", "category_id", postgresql_where=(is_deleted.is_(False))),
        Index("idx_product_status", "status", postgresql_where=(is_deleted.is_(False))),
        Index("idx_product_price", "price", postgresql_where=(is_deleted.is_(False))),
        Index("idx_product_created_at", "created_at", postgresql_where=(is_deleted.is_(False))),
    )


class ProductImage(Base):
    __tablename__ = "product_image"

    image_id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("product.product_id"), nullable=False, index=True)
    image_url = Column(String(500), nullable=False)
    alt_text = Column(String(255))
    content_type = Column(String(100))
    size_bytes = Column(BigInteger)
    is_primary = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="product_images")


class Review(Base):
    __tablename__ = "review"

    review_id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("product.product_id"), nullable=False, index=True)
    buyer_id = Column(Integer, ForeignKey("user_core.user_id"), nullable=False, index=True)
    rating = Column(SmallInteger, nullable=False)  # 1-5, or 0 for a violation report
    title = Column(String(255))
    content = Column(Text)
    is_verified_purchase = Column(Boolean, default=False)
    helpful_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False, nullable=False)

    product = relationship("Product", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")

    __table_args__ = (CheckConstraint("rating BETWEEN 0 AND 5", name="check_review_rating"),)
