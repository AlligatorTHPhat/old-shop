from datetime import datetime

from sqlalchemy import (
    DECIMAL,
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


class PaymentMethod(Base):
    __tablename__ = "payment_method"

    payment_method_id = Column(Integer, primary_key=True, index=True)
    method_name = Column(String(50), unique=True, nullable=False)
    is_online = Column(Boolean, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)

    orders = relationship("Order", back_populates="payment_method")
    transactions = relationship("Transaction", back_populates="payment_method")


class ContactInfo(Base):
    """A shipping address book entry."""

    __tablename__ = "contact_info"

    contact_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    phone_number = Column(String(15), nullable=False)
    address = Column(String(255), nullable=False)
    province = Column(String(100))
    district = Column(String(100))
    ward = Column(String(100))
    is_default = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="contact_info")
    orders = relationship("Order", back_populates="contact")


class Voucher(Base):
    __tablename__ = "voucher"

    voucher_id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    discount_type = Column(SmallInteger, default=0)  # see DiscountType
    discount_value = Column(DECIMAL(18, 2), nullable=False)
    max_usage = Column(Integer)
    usage_count = Column(Integer, default=0)
    min_order_amount = Column(DECIMAL(18, 2))
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    orders = relationship("Order", back_populates="voucher")


class Order(Base):
    __tablename__ = "order"

    order_id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("user.user_id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contact_info.contact_id"), nullable=False)
    payment_method_id = Column(Integer, ForeignKey("payment_method.payment_method_id"), nullable=False)
    voucher_id = Column(Integer, ForeignKey("voucher.voucher_id"))
    order_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_amount = Column(DECIMAL(18, 2), nullable=False)
    shipping_fee = Column(DECIMAL(18, 2), default=0)
    discount_amount = Column(DECIMAL(18, 2), default=0)
    final_amount = Column(DECIMAL(18, 2), nullable=False)
    order_status = Column(SmallInteger, default=0, nullable=False, index=True)  # see OrderStatus
    shipping_address = Column(Text)
    tracking_number = Column(String(100))
    notes = Column(Text)
    is_deleted = Column(Boolean, default=False, nullable=False)

    buyer = relationship("User", back_populates="orders")
    contact = relationship("ContactInfo", back_populates="orders")
    payment_method = relationship("PaymentMethod", back_populates="orders")
    voucher = relationship("Voucher", back_populates="orders")
    order_details = relationship("OrderDetail", back_populates="order", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="order")

    __table_args__ = (
        CheckConstraint("order_status IN (0, 1, 2, 3, 4)", name="check_order_status"),
        Index("idx_order_buyer", "buyer_id", postgresql_where=(is_deleted.is_(False))),
        Index("idx_order_status", "order_status", postgresql_where=(is_deleted.is_(False))),
        Index("idx_order_date", "order_date", postgresql_where=(is_deleted.is_(False))),
    )


class OrderDetail(Base):
    __tablename__ = "order_detail"

    order_detail_id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("order.order_id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("product.product_id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    price_at_purchase = Column(DECIMAL(18, 2), nullable=False)
    subtotal = Column(DECIMAL(18, 2), nullable=False)

    order = relationship("Order", back_populates="order_details")
    product = relationship("Product", back_populates="order_details")

    __table_args__ = (CheckConstraint("quantity > 0", name="check_order_detail_quantity"),)


class Transaction(Base):
    __tablename__ = "transaction"

    transaction_id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("order.order_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False, index=True)
    payment_method_id = Column(Integer, ForeignKey("payment_method.payment_method_id"), nullable=False)
    amount = Column(DECIMAL(18, 2), nullable=False)
    balance_before = Column(DECIMAL(18, 2), nullable=True)
    balance_after = Column(DECIMAL(18, 2), nullable=True)
    fraud_score = Column(DECIMAL(5, 2), default=0.0, nullable=True)
    provider_transaction_id = Column(String(100), nullable=True)
    transaction_status = Column(SmallInteger, default=0)  # see TransactionStatus
    reference_number = Column(String(100))
    address = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    order = relationship("Order", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    payment_method = relationship("PaymentMethod", back_populates="transactions")
