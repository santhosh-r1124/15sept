"""Password hashing, one-time tokens, and JWT access/refresh tokens.

Access tokens are short-lived and stateless (verified by signature only).
Refresh tokens are also JWTs, but carry a ``jti`` whose hash is persisted in
the ``refresh_tokens`` table (see ``app/models/user.py``) so they can be
revoked (logout) and rotated on use — a bare JWT can't be revoked, a
DB-backed one can.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import Settings

TokenType = Literal["access", "refresh"]


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash (shouldn't happen outside of corrupted data / tests).
        return False


# ---------------------------------------------------------------------------
# One-time tokens (email verification, password reset)
# ---------------------------------------------------------------------------


def hash_token(raw_token: str) -> str:
    """SHA-256 hex digest. One-time tokens are stored hashed, never in plaintext."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_one_time_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``. Send `raw_token` to the user, persist the hash."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


# ---------------------------------------------------------------------------
# JWTs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefreshTokenIssued:
    token: str
    jti: str
    expires_at: datetime


def create_access_token(*, user_id: uuid.UUID, role: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    *, user_id: uuid.UUID, role: str, settings: Settings
) -> RefreshTokenIssued:
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    expires_at = now + timedelta(days=settings.refresh_token_ttl_days)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return RefreshTokenIssued(token=token, jti=jti, expires_at=expires_at)


def decode_token(
    token: str, *, settings: Settings, expected_type: TokenType | None = None
) -> dict[str, object]:
    """Decode and verify a JWT. Raises ``jwt.PyJWTError`` on any failure.

    Set ``expected_type`` to also enforce the ``typ`` claim (access vs refresh) —
    callers should always do this to stop a refresh token being used as an
    access token or vice versa.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if expected_type is not None and payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type!r} token.")
    return payload
