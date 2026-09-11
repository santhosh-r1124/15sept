"""Service metadata — safe, unauthenticated, used by the frontends."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import SettingsDep

router = APIRouter()


class MetaResponse(BaseModel):
    name: str
    version: str
    environment: str


@router.get("/meta", summary="Service name, version and environment")
async def read_meta(settings: SettingsDep) -> MetaResponse:
    return MetaResponse(
        name=settings.app_name,
        version=settings.version,
        environment=settings.app_env.value,
    )
