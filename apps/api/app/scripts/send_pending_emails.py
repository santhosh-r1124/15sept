"""Retry notification emails that could not be sent at request time (Phase 11).

The request path makes one attempt per email and gives up quietly when the mail server is down;
the row stays PENDING in the ``notifications`` outbox. Run this from cron / a scheduled job (every
few minutes) to drain it. Rows are given up on (FAILED) after ``MAX_EMAIL_ATTEMPTS`` tries.

Usage::

    uv run python -m app.scripts.send_pending_emails
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.db.session import dispose_engine, get_sessionmaker
from app.services.email import configure_email_sender
from app.services.notifications import deliver_pending_emails


async def _run() -> None:
    configure_email_sender(get_settings())
    total = 0
    try:
        async with get_sessionmaker()() as session:
            while True:
                result = await deliver_pending_emails(session, batch_size=50)
                total += result.sent
                # Stop when the queue is drained or the mail server is failing (the failed row's
                # attempt is already recorded; the next run tries again).
                if result.failed or result.sent == 0:
                    break
        print(f"sent {total} email(s)")
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
