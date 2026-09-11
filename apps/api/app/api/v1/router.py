"""Aggregate router for API v1. Mounted at ``/api/v1`` by the app factory."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import admin, advocates, auth, chat, legal_sources, meta, users

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(advocates.router, prefix="/advocates", tags=["advocates"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(
    legal_sources.router, prefix="/admin/legal-sources", tags=["legal-sources"]
)

# Future phases register their routers here, e.g.:
#   from app.api.v1.routes import documents
#   api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
