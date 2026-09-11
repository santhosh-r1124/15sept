"""Unit tests for app.core.security — no database required."""

from __future__ import annotations

import uuid

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_one_time_token,
    hash_password,
    hash_token,
    verify_password,
)

SETTINGS = Settings(
    jwt_secret="unit-test-secret-thats-at-least-32-bytes-long",
    access_token_ttl_minutes=30,
    refresh_token_ttl_days=14,
)


def test_hash_password_is_not_plaintext_and_verifies() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_one_time_token_hash_is_deterministic_and_raw_differs() -> None:
    raw, digest = generate_one_time_token()
    assert raw != digest
    assert hash_token(raw) == digest


def test_access_token_round_trips_and_has_correct_claims() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, role="CONSUMER", settings=SETTINGS)
    payload = decode_token(token, settings=SETTINGS, expected_type="access")
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "CONSUMER"
    assert payload["typ"] == "access"


def test_refresh_token_has_jti_and_round_trips() -> None:
    user_id = uuid.uuid4()
    issued = create_refresh_token(user_id=user_id, role="ADVOCATE", settings=SETTINGS)
    payload = decode_token(issued.token, settings=SETTINGS, expected_type="refresh")
    assert payload["jti"] == issued.jti
    assert payload["sub"] == str(user_id)


def test_decode_token_rejects_wrong_type() -> None:
    token = create_access_token(user_id=uuid.uuid4(), role="CONSUMER", settings=SETTINGS)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, settings=SETTINGS, expected_type="refresh")


def test_decode_token_rejects_bad_signature() -> None:
    token = create_access_token(user_id=uuid.uuid4(), role="CONSUMER", settings=SETTINGS)
    other_settings = Settings(jwt_secret="a-completely-different-secret-thats-also-32-bytes")
    with pytest.raises(jwt.PyJWTError):
        decode_token(token, settings=other_settings, expected_type="access")


def test_decode_token_rejects_expired_token() -> None:
    expired_settings = Settings(
        jwt_secret="unit-test-secret-thats-at-least-32-bytes-long", access_token_ttl_minutes=-1
    )
    token = create_access_token(user_id=uuid.uuid4(), role="CONSUMER", settings=expired_settings)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, settings=expired_settings, expected_type="access")
