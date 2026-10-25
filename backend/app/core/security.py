import logging
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.constants import RoleId
from app.schemas.auth import TokenData

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Unknown/corrupted hash format: treat as a failed login, never as a 500.
        logger.warning("Password hash could not be verified")
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode({**data, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> TokenData | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None

    user_id = payload.get("user_id")
    if user_id is None:
        return None

    role_id = payload.get("role_id")
    if role_id is None:  # tokens issued before role_id was added carried a list
        role_ids = payload.get("role_ids") or [RoleId.USER]
        role_id = role_ids[0]

    return TokenData(user_id=user_id, username=payload.get("username", ""), role_id=role_id)
