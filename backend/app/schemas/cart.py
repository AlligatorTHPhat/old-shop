from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.catalog import ProductResponse
from app.schemas.common import ORMModel


class ShoppingCartItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)


class ShoppingCartItemResponse(ORMModel):
    cart_item_id: int
    product_id: int
    quantity: int
    added_at: datetime
    product: ProductResponse | None = None


class ShoppingCartResponse(ORMModel):
    cart_id: int
    user_id: int
    last_updated: datetime
    cart_items: list[ShoppingCartItemResponse] = []
