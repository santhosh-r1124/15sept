"""Unit tests for settings parsing — no external dependencies."""

from __future__ import annotations

from app.core.config import Environment, Settings


def test_cors_origins_accepts_comma_separated_string() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test ,http://c.test")  # type: ignore[arg-type]
    assert settings.cors_origins == [
        "http://a.test",
        "http://b.test",
        "http://c.test",
    ]


def test_cors_origins_accepts_list() -> None:
    settings = Settings(cors_origins=["http://a.test"])
    assert settings.cors_origins == ["http://a.test"]


def test_sync_url_derived_from_async_url() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@host:5432/db",
        database_url_sync=None,
    )
    assert settings.sqlalchemy_url_sync == "postgresql+psycopg://u:p@host:5432/db"


def test_sync_url_explicit_wins() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@host:5432/db",
        database_url_sync="postgresql+psycopg://other:pw@host:5432/db",
    )
    assert "other" in settings.sqlalchemy_url_sync


def test_docs_disabled_in_production() -> None:
    assert Settings(app_env=Environment.PRODUCTION).docs_enabled is False
    assert Settings(app_env=Environment.DEVELOPMENT).docs_enabled is True
