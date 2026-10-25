from fastapi import APIRouter

from app.api.v1 import admin, auth, cart, categories, moderator, orders, products, system, users

api_router = APIRouter()
for module in (auth, users, categories, products, cart, orders, moderator, admin, system):
    api_router.include_router(module.router)
