"""Create a fresh test DB on the embedded Postgres and apply every Alembic migration.

Why not ``alembic upgrade head``? On locked-down Windows machines both ``alembic.exe`` and
psycopg's native libpq can be blocked; this renders the migrations to SQL offline
(``python -m alembic upgrade head --sql``, needs no DB driver connection) and applies that
with asyncpg. ``pgcrypto``/``pg_trgm`` are contrib extensions the embedded build lacks; the
app doesn't need them (``gen_random_uuid()`` is built in since PG13), so those two
``CREATE EXTENSION`` lines are skipped here (real Docker/Supabase Postgres has them).

    uv run python dev/local_pg_migrate.py            # DB name: legal_platform_test
    uv run python dev/local_pg_migrate.py my_dev_db  # or any other name (recreated fresh!)

Then run the suite with the printed DATABASE_URL, e.g.:

    DATABASE_URL=... uv run python -m pytest -q
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys
from urllib.parse import urlparse

import asyncpg

HERE = pathlib.Path(__file__).resolve().parent
DB_NAME = sys.argv[1] if len(sys.argv) > 1 else "legal_platform_test"
SKIP = ("pgcrypto", "pg_trgm")


def main() -> None:
    state = HERE / ".local-pg.json"
    if not state.exists():
        sys.exit("Run dev/local_pg_start.py first (see its docstring).")
    parsed = urlparse(json.loads(state.read_text(encoding="utf-8"))["uri"])
    host, port, user = parsed.hostname, parsed.port, parsed.username or "postgres"
    base = f"{user}@{host}:{port}"

    env = {**os.environ, "DATABASE_URL_SYNC": f"postgresql+asyncpg://{base}/{DB_NAME}"}
    sql = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=HERE.parent,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    sql = "\n".join(line for line in sql.splitlines() if not any(s in line for s in SKIP))

    async def apply() -> None:
        admin = await asyncpg.connect(f"postgresql://{base}/postgres")
        await admin.execute(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)")
        await admin.execute(f"CREATE DATABASE {DB_NAME}")
        await admin.close()
        conn = await asyncpg.connect(f"postgresql://{base}/{DB_NAME}")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(sql)
        await conn.close()

    asyncio.run(apply())
    print(f"DATABASE_URL=postgresql+asyncpg://{base}/{DB_NAME}")


if __name__ == "__main__":
    main()
