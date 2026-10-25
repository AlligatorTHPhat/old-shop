import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import DiscountType, OrderStatus, ProductStatus, TransactionStatus
from app.core.exceptions import BadRequestError, NotFoundError
from app.crud.base import CRUDBase
from app.models import Order, OrderDetail, Product, Transaction, User, Voucher
from app.services.fraud_detection import score_transaction


def calculate_discount(voucher: Voucher, order_amount: Decimal) -> Decimal:
    if voucher.discount_type == DiscountType.FIXED:
        discount = voucher.discount_value
    else:
        discount = order_amount * (voucher.discount_value / Decimal("100"))
    return min(discount, order_amount)


class CRUDOrder(CRUDBase[Order]):
    def get_by_id(self, db: Session, order_id: int) -> Order | None:
        return db.query(Order).filter(Order.order_id == order_id, Order.is_deleted == False).first()

    def get_seller_ids(self, db: Session, order_id: int) -> set[int]:
        rows = (
            db.query(Product.seller_id)
            .join(OrderDetail, Product.product_id == OrderDetail.product_id)
            .filter(OrderDetail.order_id == order_id)
            .distinct()
            .all()
        )
        return {row[0] for row in rows}

    def get_by_buyer(
        self, db: Session, buyer_id: int, status: int | None = None, skip: int = 0, limit: int = 100
    ) -> list[Order]:
        query = db.query(Order).filter(Order.buyer_id == buyer_id, Order.is_deleted == False)
        if status is not None:
            query = query.filter(Order.order_status == status)
        return query.order_by(Order.order_date.desc()).offset(skip).limit(limit).all()

    def get_by_seller(self, db: Session, seller_id: int, skip: int = 0, limit: int = 100) -> list[Order]:
        return (
            db.query(Order)
            .join(OrderDetail)
            .join(Product)
            .filter(Product.seller_id == seller_id, Order.is_deleted == False)
            .order_by(Order.order_date.desc())
            .distinct()
            .offset(skip)
            .limit(limit)
            .all()
        )

    def find_reusable_paypal_order(self, db: Session, buyer_id: int, payment_method_id: int) -> Order | None:
        """A pending PayPal order created < 5 minutes ago is reused when the buyer retries checkout."""
        order = (
            db.query(Order)
            .filter(
                Order.buyer_id == buyer_id,
                Order.order_status == OrderStatus.PENDING,
                Order.payment_method_id == payment_method_id,
                Order.is_deleted == False,
            )
            .order_by(Order.order_date.desc())
            .first()
        )
        if order and (datetime.utcnow() - order.order_date).total_seconds() < 300:
            return order
        return None

    # ---------- vouchers ----------

    def get_valid_voucher(self, db: Session, code: str, order_amount: Decimal) -> Voucher:
        now = datetime.utcnow()
        voucher = (
            db.query(Voucher)
            .filter(Voucher.code == code.strip().upper(), Voucher.is_active == True, Voucher.is_deleted == False)
            .first()
        )
        if not voucher:
            raise NotFoundError("Mã giảm giá không tồn tại hoặc đã bị khóa.")
        if voucher.valid_from > now:
            raise BadRequestError("Mã giảm giá chưa đến thời gian sử dụng.")
        if voucher.valid_to < now:
            raise BadRequestError("Mã giảm giá đã hết hạn.")
        if voucher.max_usage is not None and voucher.usage_count >= voucher.max_usage:
            raise BadRequestError("Mã giảm giá đã hết lượt sử dụng.")
        if voucher.min_order_amount and order_amount < voucher.min_order_amount:
            raise BadRequestError(f"Đơn hàng tối thiểu {voucher.min_order_amount:,.0f}đ để dùng mã này.")
        return voucher

    # ---------- checkout ----------

    def estimate_total(self, db: Session, items: list[dict], shipping_fee: Decimal) -> Decimal:
        prices = self._load_products(db, items)
        return sum((prices[i["product_id"]].price * i["quantity"] for i in items), Decimal("0")) + shipping_fee

    def _load_products(self, db: Session, items: list[dict]) -> dict[int, Product]:
        ids = {item["product_id"] for item in items}
        products = {p.product_id: p for p in db.query(Product).filter(Product.product_id.in_(ids)).all()}
        missing = ids - products.keys()
        if missing:
            raise BadRequestError(f"Product {min(missing)} not found")
        return products

    def create_order(
        self,
        db: Session,
        buyer_id: int,
        contact_id: int,
        payment_method_id: int,
        order_items: list[dict],
        shipping_fee: Decimal = Decimal("0"),
        voucher_code: str | None = None,
        notes: str | None = None,
        shipping_address: str | None = None,
        phone_number: str | None = None,
    ) -> Order:
        products = self._load_products(db, order_items)
        total_amount = sum(
            (products[item["product_id"]].price * Decimal(item["quantity"]) for item in order_items), Decimal("0")
        )

        voucher = self.get_valid_voucher(db, voucher_code, total_amount) if voucher_code else None
        discount_amount = calculate_discount(voucher, total_amount) if voucher else Decimal("0")
        if voucher:
            voucher.usage_count += 1
        final_amount = total_amount - discount_amount + shipping_fee

        order = Order(
            buyer_id=buyer_id,
            contact_id=contact_id,
            payment_method_id=payment_method_id,
            voucher_id=voucher.voucher_id if voucher else None,
            total_amount=total_amount,
            shipping_fee=shipping_fee,
            discount_amount=discount_amount,
            final_amount=final_amount,
            notes=notes,
            shipping_address=shipping_address,
            # The schema has no phone column on orders; the receiver phone travels in tracking_number
            # until the seller replaces it with a real tracking code.
            tracking_number=phone_number,
            order_status=OrderStatus.PENDING,
        )
        db.add(order)
        db.flush()

        buyer = db.get(User, buyer_id)
        balance = buyer.balance if buyer else Decimal("0")
        risk = score_transaction(final_amount, balance)

        db.add(
            Transaction(
                order_id=order.order_id,
                user_id=buyer_id,
                payment_method_id=payment_method_id,
                amount=final_amount,
                balance_before=balance,
                balance_after=balance,  # nothing is debited while the order is pending
                reference_number=f"REF-{uuid.uuid4().hex[:8].upper()}-{order.order_id}",
                transaction_status=TransactionStatus.PENDING,
                address=shipping_address,
                fraud_score=risk.score,
            )
        )
        for item in order_items:
            product = products[item["product_id"]]
            db.add(
                OrderDetail(
                    order_id=order.order_id,
                    product_id=product.product_id,
                    quantity=item["quantity"],
                    price_at_purchase=product.price,
                    subtotal=product.price * Decimal(item["quantity"]),
                )
            )

        db.commit()
        db.refresh(order)
        return order

    def update_status(self, db: Session, order: Order, new_status: int, tracking_number: str | None = None) -> Order:
        if new_status == OrderStatus.CANCELLED and order.order_status != OrderStatus.CANCELLED:
            self._restock(order)
            if order.voucher and order.voucher.usage_count > 0:
                order.voucher.usage_count -= 1

        order.order_status = new_status
        if tracking_number:
            order.tracking_number = tracking_number
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def _restock(order: Order) -> None:
        for detail in order.order_details:
            detail.product.quantity += detail.quantity
            if detail.product.status == ProductStatus.SOLD_OUT:
                detail.product.status = ProductStatus.APPROVED


crud_order = CRUDOrder(Order)
