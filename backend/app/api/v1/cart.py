from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import any_user, get_db
from app.crud.product import crud_product
from app.crud.shopping_cart import crud_cart
from app.models import ShoppingCartItem, User
from app.schemas import ShoppingCartItemCreate, ShoppingCartItemResponse, ShoppingCartResponse

router = APIRouter(prefix="/cart", tags=["cart"])


def _get_own_item(db: Session, cart_item_id: int, user: User) -> ShoppingCartItem:
    item = crud_cart.get_item(db, cart_item_id)
    if not item or item.cart.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    return item


@router.get("", response_model=ShoppingCartResponse)
def get_cart(current_user: User = Depends(any_user), db: Session = Depends(get_db)):
    return crud_cart.get_or_create(db, current_user.user_id)


@router.post("/items", response_model=ShoppingCartItemResponse, status_code=status.HTTP_201_CREATED)
def add_cart_item(
    item_in: ShoppingCartItemCreate, current_user: User = Depends(any_user), db: Session = Depends(get_db)
):
    product = crud_product.get_by_id(db, item_in.product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.seller_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add your own product to cart")
    return crud_cart.add_item(db, current_user.user_id, item_in.product_id, item_in.quantity)


@router.put("/items/{cart_item_id}", response_model=ShoppingCartItemResponse)
def update_cart_item(
    cart_item_id: int,
    item_in: ShoppingCartItemCreate,
    current_user: User = Depends(any_user),
    db: Session = Depends(get_db),
):
    item = _get_own_item(db, cart_item_id, current_user)
    return crud_cart.update_quantity(db, item, item_in.quantity)


@router.delete("/items/{cart_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_cart_item(cart_item_id: int, current_user: User = Depends(any_user), db: Session = Depends(get_db)):
    crud_cart.remove_item(db, _get_own_item(db, cart_item_id, current_user))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(current_user: User = Depends(any_user), db: Session = Depends(get_db)):
    crud_cart.clear(db, current_user.user_id)
