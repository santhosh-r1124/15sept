"""User profile schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole


class UserOut(BaseModel):
    """Mirrors ``@legal-platform/auth`` → ``AuthUser`` (field names must match)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    email_verified: bool
    is_active: bool
    display_name: str | None
    state_code: str | None
    preferred_language: str | None
    # The tenant of an ENTERPRISE_USER (Phase 13); None for everyone else.
    organization_id: uuid.UUID | None = None


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=150)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    preferred_language: str | None = Field(default=None, max_length=50)

    @field_validator("state_code")
    @classmethod
    def _upper_state(cls, value: str | None) -> str | None:
        return value.upper() if value else value
