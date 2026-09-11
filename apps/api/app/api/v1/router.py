"""Aggregate router for API v1. Mounted at ``/api/v1`` by the app factory."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import meta

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])

# Future phases register their routers here, e.g.:
#   from app.api.v1.routes import auth, chat, advocates
#   api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
