"""Shared FastAPI dependencies: DB session, current user and role guards."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.core.constants import RoleId
from app.core.database import get_db
from app.core.security import decode_token
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_user_optional",
    "require_roles",
    "get_current_admin",
    "get_current_moderator",
    "any_user",
    "customer",
]


def _load_active_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    token_data = decode_token(token)
    if token_data is None:
        return None
    user = db.query(User).options(joinedload(User.roles)).filter(User.user_id == token_data.user_id).first()
    if user is None or user.is_deleted or not user.is_active:
        return None
    return user


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user = _load_active_user(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated" if not token else "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_optional(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User | None:
    return _load_active_user(db, token)


def require_roles(*roles: RoleId, detail: str | None = None):
    """Dependency factory: the current user must have at least one of `roles`."""

    def guard(user: User = Depends(get_current_user)) -> User:
        if not user.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail or f"User does not have permission. Required roles: {[int(r) for r in roles]}",
            )
        return user

    return guard


get_current_admin = require_roles(RoleId.ADMIN, detail="Admin role required")
get_current_moderator = require_roles(RoleId.ADMIN, RoleId.MODERATOR, detail="Bạn không có quyền Moderator!")
any_user = require_roles(RoleId.ADMIN, RoleId.MODERATOR, RoleId.USER)
customer = require_roles(RoleId.USER)
