"""Admin-only schemas: user management, advocate verification queue."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.advocate import AdvocateProfileOut
from app.schemas.user import UserOut


class PaginatedUsers(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int


class PaginatedAdvocateProfiles(BaseModel):
    items: list[AdvocateProfileOut]
    total: int
    limit: int
    offset: int


class UserActiveUpdateRequest(BaseModel):
    is_active: bool
