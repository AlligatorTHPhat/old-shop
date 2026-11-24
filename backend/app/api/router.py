from fastapi import APIRouter

from app.api.v1 import admin, auth, cart, categories, moderator, orders, products, system, users
from app.core.config import settings

api_router = APIRouter()
for module in (auth, users, categories):
    api_router.include_router(module.router)
if settings.BUCKET_MODE:
    from app.buckets.api import router as bucket_router

    api_router.include_router(bucket_router)
else:
    for module in (products, cart, orders):
        api_router.include_router(module.router)
for module in (moderator, admin, system):
    api_router.include_router(module.router)
