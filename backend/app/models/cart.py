from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.core.database import Base


class ShoppingCart(Base):
    __tablename__ = "shopping_cart"

    cart_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), unique=True, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="shopping_cart")
    cart_items = relationship("ShoppingCartItem", back_populates="cart", cascade="all, delete-orphan")


class ShoppingCartItem(Base):
    __tablename__ = "shopping_cart_item"

    cart_item_id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("shopping_cart.cart_id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("product.product_id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    cart = relationship("ShoppingCart", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")

    __table_args__ = (CheckConstraint("quantity > 0", name="check_cart_item_quantity"),)
