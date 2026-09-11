"""Aggregate router for API v1. Mounted at ``/api/v1`` by the app factory."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import admin, advocates, auth, meta, users

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(advocates.router, prefix="/advocates", tags=["advocates"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

# Future phases register their routers here, e.g.:
#   from app.api.v1.routes import chat
#   api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
