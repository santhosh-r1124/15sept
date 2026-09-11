"""One-off CLI to create or promote an admin account.

There is no public admin-registration endpoint by design. Use this to bootstrap
the first ADMIN/LEGAL_ADMIN — Phase 12 adds in-app admin management on top.

Usage::

    uv run python -m app.scripts.create_admin --email you@example.com
    uv run python -m app.scripts.create_admin --email you@example.com --role LEGAL_ADMIN
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core import security
from app.db.session import dispose_engine, get_sessionmaker
from app.models.user import User, UserRole


async def _run(email: str, password: str, role: UserRole) -> None:
    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            user = User(
                email=email.lower(),
                hashed_password=security.hash_password(password),
                role=role,
                email_verified=True,
            )
            session.add(user)
            action = "created"
        else:
            user.role = role
            user.hashed_password = security.hash_password(password)
            action = "promoted"
        await session.commit()
        print(f"{action} {email} as {role.value}")
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote an admin account.")
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--role",
        choices=[UserRole.ADMIN.value, UserRole.LEGAL_ADMIN.value],
        default=UserRole.ADMIN.value,
    )
    parser.add_argument("--password", default=None, help="Omit to be prompted (recommended).")
    args = parser.parse_args()

    password: str = args.password or getpass.getpass("Password: ")
    asyncio.run(_run(args.email, password, UserRole(args.role)))


if __name__ == "__main__":
    main()
