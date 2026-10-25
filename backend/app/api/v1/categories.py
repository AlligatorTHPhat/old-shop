from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.crud.category import crud_category
from app.models import Category, User
from app.schemas import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


def _get_or_404(db: Session, category_id: int, include_deleted: bool = False) -> Category:
    category = crud_category.get_by_id(db, category_id, include_deleted=include_deleted)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


def _ensure_parent_exists(db: Session, parent_id: int | None) -> None:
    if parent_id and not crud_category.get_by_id(db, parent_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent category not found")


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(False),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
):
    return crud_category.get_list(db, skip, limit, active_only=active_only, include_deleted=include_deleted)


@router.get("/parent", response_model=list[CategoryResponse])
def list_parent_categories(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)
):
    return crud_category.get_parents(db, skip=skip, limit=limit)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, category_id)


@router.get("/{category_id}/children", response_model=list[CategoryResponse])
def get_category_children(
    category_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    _get_or_404(db, category_id)
    return crud_category.get_children(db, parent_id=category_id, skip=skip, limit=limit)


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category_in: CategoryCreate, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    if crud_category.get_by_name(db, category_in.name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name already exists")
    _ensure_parent_exists(db, category_in.parent_id)
    return crud_category.create(db, category_in)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_update: CategoryUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    category = _get_or_404(db, category_id)
    if (
        category_update.name
        and category_update.name != category.name
        and crud_category.get_by_name(db, category_update.name)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name already exists")
    if category_update.parent_id != category.parent_id:
        _ensure_parent_exists(db, category_update.parent_id)
    return crud_category.update(db, category, category_update)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Soft delete. The category must be deactivated first."""
    category = _get_or_404(db, category_id)
    if category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phải vô hiệu hóa danh mục trước khi xóa")
    crud_category.soft_delete_with_products(db, category)


@router.delete("/{category_id}/hard-delete", status_code=status.HTTP_204_NO_CONTENT)
def hard_delete_category(category_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    category = _get_or_404(db, category_id, include_deleted=True)
    if not category.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Danh mục phải nằm trong trạng thái xóa mềm trước khi xóa vĩnh viễn",
        )
    if crud_category.has_products(db, category_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Không thể xóa vĩnh viễn danh mục đang chứa sản phẩm"
        )
    crud_category.hard_delete(db, category)


@router.post("/{category_id}/restore", response_model=CategoryResponse)
def restore_category(category_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    category = _get_or_404(db, category_id, include_deleted=True)
    if not category.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Danh mục không ở trạng thái xóa mềm")
    return crud_category.restore(db, category)
