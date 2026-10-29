from sqlalchemy.orm import Query, Session, joinedload

from app.core.constants import ProductStatus
from app.core.exceptions import BadRequestError, NotFoundError
from app.crud.base import CRUDBase
from app.models import Category, Product, ProductImage, Review
from app.schemas import ReviewCreate
from app.services.storage import image_metadata

SORT_COLUMNS = {
    "created_at": Product.created_at.desc(),
    "price": Product.price.asc(),
    "rating": Product.view_count.desc(),  # no rating aggregate yet; popularity is the proxy
}


class CRUDProduct(CRUDBase[Product]):
    def _visible(self, db: Session) -> Query:
        """Approved, not deleted, and in a live category."""
        return (
            db.query(Product)
            .join(Category, Product.category_id == Category.category_id)
            .options(joinedload(Product.product_images))
            .filter(
                Product.status == ProductStatus.APPROVED,
                Product.is_deleted == False,
                Category.is_deleted == False,
            )
        )

    def get_by_id(self, db: Session, product_id: int) -> Product | None:
        return (
            db.query(Product)
            .options(
                joinedload(Product.product_images),
                joinedload(Product.reviews).joinedload(Review.reviewer),
                joinedload(Product.seller),
            )
            .filter(Product.product_id == product_id, Product.is_deleted == False)
            .first()
        )

    def get_approved(self, db: Session, skip: int = 0, limit: int = 100, order_by: str = "created_at") -> list[Product]:
        return (
            self._visible(db)
            .filter(Category.is_active == True)
            .order_by(SORT_COLUMNS.get(order_by, SORT_COLUMNS["created_at"]))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_category(
        self, db: Session, category_id: int, skip: int = 0, limit: int = 100, order_by: str = "created_at"
    ) -> list[Product]:
        return (
            self._visible(db)
            .filter(Product.category_id == category_id)
            .order_by(SORT_COLUMNS.get(order_by, SORT_COLUMNS["created_at"]))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def search(self, db: Session, query_str: str, skip: int = 0, limit: int = 100) -> list[Product]:
        pattern = f"%{query_str}%"
        return (
            self._visible(db)
            .options(joinedload(Product.seller))
            .filter(Product.title.ilike(pattern) | Product.description.ilike(pattern))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_seller(self, db: Session, seller_id: int, skip: int = 0, limit: int = 100) -> list[Product]:
        return (
            db.query(Product)
            .options(joinedload(Product.product_images))
            .filter(Product.seller_id == seller_id, Product.is_deleted == False)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_status(self, db: Session, status: int, skip: int = 0, limit: int = 100) -> list[Product]:
        return (
            db.query(Product)
            .options(joinedload(Product.product_images))
            .filter(Product.status == status, Product.is_deleted == False)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def add_pending(self, db: Session, data: dict) -> Product:
        """Insert a product awaiting moderation. Flushes only; the caller commits."""
        product = Product(**data, status=ProductStatus.PENDING)
        db.add(product)
        db.flush()
        return product

    def add_images(self, db: Session, product: Product, image_urls: list[str]) -> None:
        for order, url in enumerate(image_urls, start=1):
            db.add(
                ProductImage(
                    product_id=product.product_id,
                    image_url=url,
                    **image_metadata(url),
                    alt_text=f"{product.title} - Image {order}",
                    is_primary=order == 1,
                    display_order=order,
                )
            )

    def increment_view_count(self, db: Session, product: Product) -> None:
        product.view_count = (product.view_count or 0) + 1
        db.commit()

    def moderate(
        self, db: Session, product: Product, status: int, moderator_id: int, reject_reason: str | None = None
    ) -> Product:
        if status not in (ProductStatus.PENDING, ProductStatus.APPROVED, ProductStatus.REJECTED):
            raise BadRequestError("Invalid status value")
        if status == ProductStatus.REJECTED and not reject_reason:
            raise BadRequestError("Cần lý do khi từ chối sản phẩm")

        product.status = status
        product.reject_reason = reject_reason if status == ProductStatus.REJECTED else None
        if status != ProductStatus.PENDING:
            product.approved_by = moderator_id
        db.commit()
        db.refresh(product)
        return product

    def get_for_moderation(self, db: Session, product_id: int) -> Product:
        product = self.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")
        return product

    def create_review(self, db: Session, product_id: int, review_in: ReviewCreate, buyer_id: int) -> Review:
        if not db.query(Product.product_id).filter(Product.product_id == product_id).first():
            raise NotFoundError("Product not found")
        review = Review(
            product_id=product_id,
            buyer_id=buyer_id,
            rating=review_in.rating,  # 0 means "report"
            title=review_in.title,
            content=review_in.content,
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review


crud_product = CRUDProduct(Product)
