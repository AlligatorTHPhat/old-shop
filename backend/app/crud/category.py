from sqlalchemy.orm import Session

from app.core.constants import ProductStatus
from app.crud.base import CRUDBase
from app.models import Category, Product


class CRUDCategory(CRUDBase[Category]):
    def get_by_id(self, db: Session, category_id: int, include_deleted: bool = False) -> Category | None:
        query = db.query(Category).filter(Category.category_id == category_id)
        if not include_deleted:
            query = query.filter(Category.is_deleted == False)
        return query.first()

    def get_by_name(self, db: Session, name: str) -> Category | None:
        return db.query(Category).filter(Category.name == name, Category.is_deleted == False).first()

    def get_list(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
        include_deleted: bool = False,
    ) -> list[Category]:
        query = db.query(Category)
        if not include_deleted:
            query = query.filter(Category.is_deleted == False)
        if active_only:
            query = query.filter(Category.is_active == True)
        return query.offset(skip).limit(limit).all()

    def get_parents(self, db: Session, skip: int = 0, limit: int = 100) -> list[Category]:
        return (
            db.query(Category)
            .filter(Category.parent_id.is_(None), Category.is_active == True, Category.is_deleted == False)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_children(self, db: Session, parent_id: int, skip: int = 0, limit: int = 100) -> list[Category]:
        return (
            db.query(Category)
            .filter(Category.parent_id == parent_id, Category.is_deleted == False)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def has_products(self, db: Session, category_id: int) -> bool:
        return db.query(Product.product_id).filter(Product.category_id == category_id).first() is not None

    def soft_delete_with_products(self, db: Session, category: Category) -> None:
        """Trash the category and send its products back to moderation."""
        category.is_deleted = True
        db.query(Product).filter(Product.category_id == category.category_id).update(
            {Product.status: ProductStatus.PENDING}, synchronize_session=False
        )
        db.commit()

    def restore(self, db: Session, category: Category) -> Category:
        category.is_deleted = False
        db.commit()
        db.refresh(category)
        return category


crud_category = CRUDCategory(Category)
