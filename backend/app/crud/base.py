from typing import Any

from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.orm import Session


class CRUDBase[ModelT]:
    """Generic data access helpers. Models use table-specific PK names (user_id, product_id...)."""

    def __init__(self, model: type[ModelT]):
        self.model = model
        self._pk = inspect(model).primary_key[0]

    def get(self, db: Session, id: Any) -> ModelT | None:
        return db.query(self.model).filter(self._pk == id).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100, include_deleted: bool = False) -> list[ModelT]:
        query = db.query(self.model)
        if not include_deleted and hasattr(self.model, "is_deleted"):
            query = query.filter(self.model.is_deleted == False)
        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: BaseModel | dict) -> ModelT:
        data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        db_obj = self.model(**data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: ModelT, obj_in: BaseModel | dict) -> ModelT:
        data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            if value is not None and hasattr(db_obj, field):
                setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def soft_delete(self, db: Session, db_obj: ModelT) -> None:
        db_obj.is_deleted = True
        db.add(db_obj)
        db.commit()

    def hard_delete(self, db: Session, db_obj: ModelT) -> None:
        db.delete(db_obj)
        db.commit()
