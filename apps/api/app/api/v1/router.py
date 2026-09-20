"""Aggregate router for API v1. Mounted at ``/api/v1`` by the app factory."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    admin_ops,
    advocate_portal,
    advocates,
    auth,
    calls,
    chat,
    documents,
    legal_sources,
    matter_documents,
    matters,
    meta,
    notifications,
    payments,
    users,
)

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(advocates.router, prefix="/advocates", tags=["advocates"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_ops.router, prefix="/admin", tags=["admin-ops"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(
    legal_sources.router, prefix="/admin/legal-sources", tags=["legal-sources"]
)
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(matters.router, prefix="/matters", tags=["matters"])
api_router.include_router(matter_documents.router, prefix="/matters", tags=["matter-documents"])
api_router.include_router(calls.router, prefix="/matters", tags=["calls"])
api_router.include_router(advocate_portal.router, prefix="/advocates/me", tags=["advocate-portal"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(payments.admin_router, prefix="/admin/payments", tags=["admin-payments"])
