import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import any_user, customer, get_current_admin, get_db
from app.core.constants import OrderStatus, RoleId, TransactionStatus
from app.crud.order import calculate_discount, crud_order
from app.crud.shopping_cart import crud_cart
from app.models import ContactInfo, Order, PaymentMethod, Product, Transaction, User
from app.schemas import (
    OrderCreate,
    OrderResponse,
    OrderUpdate,
    OrderWithDetailsResponse,
    PaymentMethodResponse,
    VoucherCheckResponse,
)
from app.services import paypal
from app.services.fraud_detection import score_transaction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])


def _get_order_for(db: Session, order_id: int, user: User) -> tuple[Order, bool, bool]:
    """Return the order plus (is_admin, is_seller) flags; 403 if the user has nothing to do with it."""
    order = crud_order.get_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    is_admin = user.has_role(RoleId.ADMIN)
    is_seller = user.user_id in crud_order.get_seller_ids(db, order_id)
    if not (is_admin or is_seller or order.buyer_id == user.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return order, is_admin, is_seller


def _get_own_contact(db: Session, contact_id: int, user: User) -> ContactInfo:
    contact = (
        db.query(ContactInfo)
        .filter(
            ContactInfo.contact_id == contact_id,
            ContactInfo.user_id == user.user_id,
            ContactInfo.is_deleted == False,
        )
        .first()
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact information")
    return contact


def _validate_items(db: Session, order_in: OrderCreate, buyer: User) -> None:
    ids = [item.product_id for item in order_in.order_items]
    products = {p.product_id: p for p in db.query(Product).filter(Product.product_id.in_(ids)).all()}
    for product_id in ids:
        product = products.get(product_id)
        if not product or product.is_deleted:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product {product_id} not found")
        if product.seller_id == buyer.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"You cannot order your own product '{product.title}'"
            )


def _place_order(db: Session, order_in: OrderCreate, buyer: User, contact: ContactInfo) -> Order:
    return crud_order.create_order(
        db=db,
        buyer_id=buyer.user_id,
        contact_id=order_in.contact_id,
        payment_method_id=order_in.payment_method_id,
        order_items=[item.model_dump() for item in order_in.order_items],
        shipping_fee=order_in.shipping_fee,
        voucher_code=order_in.voucher_code,
        notes=order_in.notes,
        shipping_address=order_in.shipping_address or contact.address,
        phone_number=order_in.phone_number or contact.phone_number,
    )


# ---------- lookups ----------


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
def get_payment_methods(db: Session = Depends(get_db)):
    return db.query(PaymentMethod).filter(PaymentMethod.is_deleted == False).all()


@router.get("/check-voucher/{code}", response_model=VoucherCheckResponse)
def check_voucher(
    code: str,
    order_amount: float = Query(..., description="Order subtotal, shipping excluded"),
    current_user: User = Depends(customer),
    db: Session = Depends(get_db),
):
    amount = Decimal(str(order_amount))
    voucher = crud_order.get_valid_voucher(db, code, amount)
    return VoucherCheckResponse(
        voucher_id=voucher.voucher_id,
        code=voucher.code,
        discount_type=voucher.discount_type,
        discount_value=float(voucher.discount_value),
        calculated_discount=float(calculate_discount(voucher, amount)),
        description=voucher.description,
    )


@router.get("/seller", response_model=list[OrderResponse])
def get_seller_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(customer),
    db: Session = Depends(get_db),
):
    return crud_order.get_by_seller(db, seller_id=current_user.user_id, skip=skip, limit=limit)


@router.get("", response_model=list[OrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status_filter: int | None = Query(None),
    current_user: User = Depends(customer),
    db: Session = Depends(get_db),
):
    return crud_order.get_by_buyer(db, current_user.user_id, status=status_filter, skip=skip, limit=limit)


@router.get("/{order_id}", response_model=OrderWithDetailsResponse)
def get_order(order_id: int, current_user: User = Depends(any_user), db: Session = Depends(get_db)):
    order, _, _ = _get_order_for(db, order_id, current_user)
    return order


# ---------- COD checkout & lifecycle ----------


@router.post("", response_model=OrderWithDetailsResponse, status_code=status.HTTP_201_CREATED)
def create_order(order_in: OrderCreate, current_user: User = Depends(customer), db: Session = Depends(get_db)):
    contact = _get_own_contact(db, order_in.contact_id, current_user)
    if not db.query(PaymentMethod).filter_by(payment_method_id=order_in.payment_method_id, is_deleted=False).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment method")
    _validate_items(db, order_in, current_user)

    order = _place_order(db, order_in, current_user, contact)
    crud_cart.remove_ordered_products(db, current_user.user_id, [i.product_id for i in order_in.order_items])
    logger.info("Order placed", extra={"order_id": order.order_id, "amount": str(order.final_amount)})
    db.refresh(order)
    return order


@router.put("/{order_id}", response_model=OrderResponse)
def update_order(
    order_id: int,
    order_update: OrderUpdate,
    current_user: User = Depends(any_user),
    db: Session = Depends(get_db),
):
    order, is_admin, is_seller = _get_order_for(db, order_id, current_user)
    new_status = order_update.order_status if order_update.order_status is not None else order.order_status

    if new_status in (OrderStatus.CONFIRMED, OrderStatus.SHIPPING, OrderStatus.DELIVERED) and not (
        is_admin or is_seller
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only seller/admin can confirm/ship orders")
    if new_status == OrderStatus.CANCELLED and order.order_status == OrderStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is already cancelled")

    return crud_order.update_status(db, order, new_status, tracking_number=order_update.tracking_number)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    order = crud_order.get_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    crud_order.soft_delete(db, order)


# ---------- PayPal checkout ----------


@router.post("/create-paypal-order")
async def create_paypal_order(
    order_in: OrderCreate,
    bypass_fraud: bool = Query(False, description="Set by the client after the 60s cool-down + re-verification"),
    current_user: User = Depends(customer),
    db: Session = Depends(get_db),
):
    _validate_items(db, order_in, current_user)

    # Risk is assessed before anything else so a blocked buyer learns nothing about the rest of the payload.
    estimate = crud_order.estimate_total(db, [i.model_dump() for i in order_in.order_items], order_in.shipping_fee)
    risk = score_transaction(estimate, current_user.balance)
    if risk.is_fraud:
        logger.warning("Checkout blocked by fraud check", extra={"user_id": current_user.user_id, "score": risk.score})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Giao dịch bị từ chối do rủi ro quá cao.")
    if risk.is_suspicious and not bypass_fraud:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "Phát hiện hành vi bất thường. Vui lòng xác thực lại sau 60 giây.", "retry_after": 60},
        )

    contact = _get_own_contact(db, order_in.contact_id, current_user)

    # A voucher changes the amount, so only voucher-less retries may reuse a recent pending order.
    order = None
    if not order_in.voucher_code:
        order = crud_order.find_reusable_paypal_order(db, current_user.user_id, order_in.payment_method_id)
    order = order or _place_order(db, order_in, current_user, contact)

    paypal_order = await paypal.create_order(order.order_id, order.final_amount)
    return {"paypal": paypal_order, "internal_order_id": order.order_id}


@router.post("/{order_id}/capture-paypal")
async def capture_paypal_payment(
    order_id: int,
    paypal_order_id: str = Query(...),
    current_user: User = Depends(customer),
    db: Session = Depends(get_db),
):
    order = crud_order.get_by_id(db, order_id)
    if not order or order.buyer_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    result = await paypal.capture_order(paypal_order_id)
    if result.get("status") != "COMPLETED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PayPal Capture failed")

    db.refresh(current_user)
    risk = score_transaction(order.final_amount, current_user.balance)
    crud_cart.remove_ordered_products(db, current_user.user_id, [d.product_id for d in order.order_details])

    transaction = db.query(Transaction).filter(Transaction.order_id == order_id).first()
    if risk.is_fraud:
        order.order_status = OrderStatus.PENDING
        message = "Giao dịch bị tạm giữ do rủi ro cao."
    else:
        order.order_status = OrderStatus.CONFIRMED
        message = "Thanh toán thành công."
    if transaction:
        transaction.fraud_score = risk.score
        transaction.provider_transaction_id = paypal_order_id
        transaction.transaction_status = TransactionStatus.FLAGGED if risk.is_fraud else TransactionStatus.SUCCESS
    db.commit()

    logger.info("PayPal payment captured", extra={"order_id": order_id, "fraud": risk.is_fraud})
    return {"status": "success", "fraud_detected": risk.is_fraud, "detail": message}
