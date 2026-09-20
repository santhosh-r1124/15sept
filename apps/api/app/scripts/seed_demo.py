"""Seed a local/staging database with demo accounts so the UI has something to show.

    cd apps/api && uv run python -m app.scripts.seed_demo

Creates (idempotently, keyed by email): one consumer, one admin, and a handful of VERIFIED
advocates across practice areas and cities. Every account uses the same well-known demo
password, so this refuses to run in production.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core import security
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.user import AdvocateProfile, User, UserRole, VerificationStatus

DEMO_PASSWORD = "DemoPass#2026"

CONSUMER = ("consumer@demo.legal", "Demo Consumer")
ADMIN = ("admin@demo.legal", "Demo Admin")

# (email, name, state, city, practice_areas, languages, fee, years, bio)
ADVOCATES: list[tuple[str, str, str, str, list[str], list[str], str, int, str]] = [
    (
        "kavya@demo.legal",
        "Adv. Kavya Rao",
        "KA",
        "Bengaluru",
        ["IT_LAW", "DATA_PROTECTION", "CONTRACT_LAW"],
        ["en", "kn", "hi"],
        "1500.00",
        9,
        "Technology and data-protection counsel for startups; DPDP Act readiness reviews.",
    ),
    (
        "arjun@demo.legal",
        "Adv. Arjun Mehta",
        "MH",
        "Mumbai",
        ["CORPORATE_LAW", "CONTRACT_LAW"],
        ["en", "hi", "mr"],
        "2500.00",
        15,
        "Company formation, shareholder agreements and commercial contracts.",
    ),
    (
        "meera@demo.legal",
        "Adv. Meera Iyer",
        "TN",
        "Chennai",
        ["FAMILY_LAW", "PROPERTY_LAW"],
        ["en", "ta"],
        "1000.00",
        6,
        "Family and property matters, rental and sale agreements, registration guidance.",
    ),
    (
        "rohan@demo.legal",
        "Adv. Rohan Singh",
        "DL",
        "New Delhi",
        ["CONSUMER_LAW", "EMPLOYMENT_LAW", "CRIMINAL_LAW"],
        ["en", "hi", "pa"],
        "1800.00",
        12,
        "Consumer forums, employment disputes and legal notices.",
    ),
]


async def main() -> None:
    settings = get_settings()
    if settings.app_env.is_production:
        raise SystemExit("Refusing to seed demo accounts in production.")

    hashed = security.hash_password(DEMO_PASSWORD)
    created: list[str] = []
    async with get_sessionmaker()() as session:

        async def ensure_user(email: str, name: str, role: UserRole, state: str | None) -> User:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    email=email,
                    hashed_password=hashed,
                    role=role,
                    display_name=name,
                    state_code=state,
                    email_verified=True,
                )
                session.add(user)
                await session.flush()
                created.append(email)
            return user

        await ensure_user(CONSUMER[0], CONSUMER[1], UserRole.CONSUMER, None)
        await ensure_user(ADMIN[0], ADMIN[1], UserRole.ADMIN, None)
        for email, name, state, city, areas, langs, fee, years, bio in ADVOCATES:
            user = await ensure_user(email, name, UserRole.ADVOCATE, state)
            has_profile = await session.scalar(
                select(AdvocateProfile.id).where(AdvocateProfile.user_id == user.id)
            )
            if has_profile is None:
                session.add(
                    AdvocateProfile(
                        user_id=user.id,
                        practice_areas=areas,
                        state_code=state,
                        city=city,
                        languages=langs,
                        consultation_fee=Decimal(fee),
                        experience_years=years,
                        bio=bio,
                        verification_status=VerificationStatus.VERIFIED,
                    )
                )
        await session.commit()

    print(f"Seeded {len(created)} new account(s); demo password: {DEMO_PASSWORD}")
    print(f"  consumer: {CONSUMER[0]}\n  admin:    {ADMIN[0]}")
    for adv in ADVOCATES:
        print(f"  advocate: {adv[0]}")


if __name__ == "__main__":
    asyncio.run(main())
