"""Shopping cart.

Stock is *reserved* when an item is added to the cart (product.quantity goes
down) and released when it is removed. Rows are locked with SELECT ... FOR
UPDATE so two buyers cannot reserve the last unit at the same time.
"""

from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.core.constants import ProductStatus
from app.core.exceptions import BadRequestError
from app.models import Product, ShoppingCart, ShoppingCartItem


def _release_stock(product: Product, quantity: int) -> None:
    product.quantity += quantity
    if product.quantity > 0 and product.status == ProductStatus.SOLD_OUT:
        product.status = ProductStatus.APPROVED


def _reserve_stock(product: Product, quantity: int) -> None:
    if product.quantity < quantity:
        raise BadRequestError(f"Sản phẩm hiện chỉ còn {product.quantity} món. Vui lòng giảm số lượng!")
    product.quantity -= quantity
    if product.quantity == 0:
        product.status = ProductStatus.SOLD_OUT


class CRUDShoppingCart:
    def get_by_user_id(self, db: Session, user_id: int) -> ShoppingCart | None:
        return (
            db.query(ShoppingCart)
            .options(joinedload(ShoppingCart.cart_items).joinedload(ShoppingCartItem.product))
            .filter(ShoppingCart.user_id == user_id)
            .first()
        )

    def get_or_create(self, db: Session, user_id: int) -> ShoppingCart:
        cart = self.get_by_user_id(db, user_id)
        if cart:
            return cart
        cart = ShoppingCart(user_id=user_id, last_updated=datetime.utcnow())
        db.add(cart)
        db.commit()
        db.refresh(cart)
        return cart

    def get_item(self, db: Session, cart_item_id: int) -> ShoppingCartItem | None:
        return db.query(ShoppingCartItem).filter(ShoppingCartItem.cart_item_id == cart_item_id).first()

    def _lock_product(self, db: Session, product_id: int, approved_only: bool = False) -> Product | None:
        query = db.query(Product).filter(Product.product_id == product_id)
        if approved_only:
            query = query.filter(Product.is_deleted == False, Product.status == ProductStatus.APPROVED)
        return query.with_for_update().first()

    def add_item(self, db: Session, user_id: int, product_id: int, quantity: int) -> ShoppingCartItem:
        product = self._lock_product(db, product_id, approved_only=True)
        if not product:
            raise BadRequestError("Sản phẩm không tồn tại hoặc đã bị xóa")
        _reserve_stock(product, quantity)

        cart = self.get_or_create(db, user_id)
        item = (
            db.query(ShoppingCartItem)
            .filter(ShoppingCartItem.cart_id == cart.cart_id, ShoppingCartItem.product_id == product_id)
            .first()
        )
        if item:
            item.quantity += quantity
        else:
            item = ShoppingCartItem(cart_id=cart.cart_id, product_id=product_id, quantity=quantity)
            db.add(item)

        cart.last_updated = datetime.utcnow()
        db.commit()
        db.refresh(item)
        return item

    def update_quantity(self, db: Session, item: ShoppingCartItem, quantity: int) -> ShoppingCartItem:
        product = self._lock_product(db, item.product_id)
        diff = quantity - item.quantity
        if diff > 0:
            _reserve_stock(product, diff)
        elif diff < 0:
            _release_stock(product, -diff)

        item.quantity = quantity
        item.added_at = datetime.utcnow()
        item.cart.last_updated = datetime.utcnow()
        db.commit()
        db.refresh(item)
        return item

    def remove_item(self, db: Session, item: ShoppingCartItem) -> None:
        product = self._lock_product(db, item.product_id)
        if product:
            _release_stock(product, item.quantity)
        item.cart.last_updated = datetime.utcnow()
        db.delete(item)
        db.commit()

    def clear(self, db: Session, user_id: int) -> None:
        cart = self.get_by_user_id(db, user_id)
        if not cart:
            return
        for item in list(cart.cart_items):
            product = self._lock_product(db, item.product_id)
            if product:
                _release_stock(product, item.quantity)
            db.delete(item)
        cart.last_updated = datetime.utcnow()
        db.commit()

    def remove_ordered_products(self, db: Session, user_id: int, product_ids: list[int]) -> None:
        """After checkout the reserved stock is consumed, so items are dropped without releasing it."""
        cart = db.query(ShoppingCart).filter(ShoppingCart.user_id == user_id).first()
        if not cart or not product_ids:
            return
        db.query(ShoppingCartItem).filter(
            ShoppingCartItem.cart_id == cart.cart_id,
            ShoppingCartItem.product_id.in_(product_ids),
        ).delete(synchronize_session=False)
        db.commit()


crud_cart = CRUDShoppingCart()
