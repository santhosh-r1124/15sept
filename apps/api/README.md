# legal-platform-api

FastAPI backend for the Indian Legal Advisor platform.

## Layout

```
app/
├── main.py              # app factory, middleware, lifespan, exception handlers
├── core/
│   ├── config.py        # pydantic-settings — typed env config + Environment
│   ├── logging.py       # structlog setup (console dev / JSON prod)
│   ├── errors.py        # AppError hierarchy + handlers + error envelope
│   └── security.py      # password hashing, one-time tokens, JWT access/refresh
├── db/
│   ├── base.py          # SQLAlchemy DeclarativeBase + naming convention
│   └── session.py       # async engine + sessionmaker lifecycle
├── models/
│   ├── user.py            # User, AdvocateProfile, *Token tables (Phase 1)
│   └── chat.py            # Conversation, ChatMessage (Phase 2)
├── schemas/              # Pydantic request/response models (auth, user, advocate, admin, chat)
├── middleware/
│   └── request_context.py  # request-id, structured access log, timing
├── services/
│   ├── redis.py          # async Redis client lifecycle
│   ├── email.py          # EmailSender abstraction (dev: logs; Phase 11: real provider)
│   ├── tokens.py          # issue + persist an access/refresh token pair
│   └── llm.py             # Claude: query classification + answer generation (Phase 2)
├── scripts/
│   └── create_admin.py    # CLI to bootstrap an ADMIN/LEGAL_ADMIN account
└── api/
    ├── deps.py            # get_db, get_redis, get_current_user(_optional), require_roles(...)
    └── v1/
        ├── router.py       # /api/v1 aggregate router
        └── routes/
            ├── health.py    # /health, /health/ready
            ├── meta.py       # /api/v1/meta
            ├── auth.py       # register/login/refresh/logout, verify email, password reset
            ├── users.py      # GET/PATCH /api/v1/users/me
            ├── advocates.py  # advocate self-registration + own-profile
            ├── admin.py      # user list/suspend, advocate verification queue (RBAC)
            └── chat.py       # send message (anon or logged in), list/get conversations
```

## Develop

```bash
uv sync                                   # create .venv, install deps
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs> — click **Authorize** and paste an access
token from `/auth/register` or `/auth/login` to call protected routes.

## Auth model (Phase 1)

- Access tokens: short-lived JWTs (`ACCESS_TOKEN_TTL_MINUTES`), verified by
  signature only.
- Refresh tokens: JWTs with a `jti`, hashed and stored in `refresh_tokens` so
  they can be revoked (logout) and are rotated (single-use) on every
  `/auth/refresh` call.
- RBAC: `Depends(require_roles(UserRole.ADMIN, UserRole.LEGAL_ADMIN))` — see
  `app/api/v1/routes/admin.py` for the pattern.
- No public admin-registration endpoint. Bootstrap the first admin with:

  ```bash
  uv run python -m app.scripts.create_admin --email you@example.com
  ```

- Emails (verification, password reset) are logged, not sent, until Phase 11
  wires a real provider behind `app/services/email.py::EmailSender`. Read the
  link out of the API's log output in development.

## Chat (Phase 2)

`POST /api/v1/chat/messages` works with or without a bearer token (public
tier). One Claude call classifies the message (`app/services/llm.py::classify_query`
— legal category, jurisdiction scope, in/out of scope); a second call
generates the answer only when in scope. **No retrieval grounding yet** —
that's `services/document-processing` (Phase 3) and `services/rag` (Phase 4);
the system prompt instructs the model to defer to an advocate rather than
invent specifics in the meantime.

Requires `ANTHROPIC_API_KEY` in `apps/api/.env` — unset by default. Without
it the endpoint returns `503 {"error": {"code": "llm_not_configured"}}`
rather than failing silently or guessing.

## Migrations (Alembic)

```bash
uv run alembic upgrade head                       # apply
uv run alembic revision --autogenerate -m "add users"   # create
uv run alembic downgrade -1                        # roll back one
```

Alembic reads `DATABASE_URL_SYNC` (psycopg driver). Autogenerate compares
`app.db.base.Base.metadata` against the live DB, so every model module must be
imported in `app/models/__init__.py`. Hand-written migrations that use a
Postgres native enum (`user_role`, `verification_status`, `message_role`)
follow the `create_type=False` + explicit `.create()`/`.drop()` pattern — see
`migrations/versions/20260102_0000-0002_auth_tables.py`.

## Testing

Two fixtures, in `tests/conftest.py`:

- `client` — no database. Use for anything that never reaches a DB session
  (health checks, "missing/invalid token" RBAC cases).
- `db_client` — every request runs inside one outer transaction that's rolled
  back after the test, so tests are isolated and never leave rows behind.
  **Skips automatically** if Postgres isn't reachable — start it first with
  `pnpm stack:up` (repo root) to actually run these.

```bash
uv run pytest -q             # unit + RBAC tests always run; DB tests skip without Postgres
pnpm stack:up                # from repo root — brings up Postgres + Redis
uv run alembic upgrade head
uv run pytest -q             # now the full suite runs
```

## Quality gates

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest --cov
```
