"""Advocate registration / profile schemas."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import VerificationStatus


class AdvocateRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(max_length=150)
    practice_areas: list[str] = Field(default_factory=list, max_length=20)
    state_code: str = Field(min_length=2, max_length=2)
    city: str = Field(min_length=1, max_length=100)
    languages: list[str] = Field(default_factory=list, max_length=20)
    consultation_fee: Decimal | None = Field(default=None, ge=0)
    bio: str | None = Field(default=None, max_length=2000)
    experience_years: int | None = Field(default=None, ge=0, le=70)

    @field_validator("state_code")
    @classmethod
    def _upper_state(cls, value: str) -> str:
        return value.upper()


class AdvocateProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    practice_areas: list[str]
    state_code: str
    city: str
    languages: list[str]
    consultation_fee: Decimal | None
    bio: str | None
    experience_years: int | None
    verification_status: VerificationStatus
    verification_note: str | None
    availability: dict[str, object] | None


class AdvocateProfileUpdateRequest(BaseModel):
    practice_areas: list[str] | None = Field(default=None, max_length=20)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    languages: list[str] | None = Field(default=None, max_length=20)
    consultation_fee: Decimal | None = Field(default=None, ge=0)
    bio: str | None = Field(default=None, max_length=2000)
    experience_years: int | None = Field(default=None, ge=0, le=70)
    availability: dict[str, object] | None = None

    @field_validator("state_code")
    @classmethod
    def _upper_state(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class AdvocateVerifyRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AdvocateRejectRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class AdvocateDirectoryEntry(BaseModel):
    """Public-facing advocate listing (Phase 7) — deliberately narrower than
    ``AdvocateProfileOut``: adds ``display_name`` (lives on ``User``, not
    ``AdvocateProfile``) and omits ``verification_note`` (an internal
    moderation note, never shown to consumers). Every entry is implicitly
    VERIFIED — search only ever returns verified advocates — so the status
    itself isn't repeated on each row.
    """

    id: uuid.UUID
    display_name: str | None
    practice_areas: list[str]
    state_code: str
    city: str
    languages: list[str]
    consultation_fee: Decimal | None
    bio: str | None
    experience_years: int | None
    availability: dict[str, object] | None


class PaginatedAdvocateDirectory(BaseModel):
    items: list[AdvocateDirectoryEntry]
    total: int
    limit: int
    offset: int
