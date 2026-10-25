"""Domain errors raised by the CRUD/service layer.

They carry an HTTP status so routers don't need try/except boilerplate: the
handler registered in app.main turns them into `{"detail": ...}` responses,
which is the same shape FastAPI uses for HTTPException.
"""

from fastapi import status


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
