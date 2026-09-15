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
│   ├── chat.py            # Conversation, ChatMessage (Phase 2)
│   └── legal_document.py   # LegalDocument, LegalChunk (pgvector) (Phase 3)
├── schemas/              # Pydantic request/response models (auth, user, advocate, admin, chat, legal_source)
├── middleware/
│   └── request_context.py  # request-id, structured access log, timing
├── services/
│   ├── redis.py            # async Redis client lifecycle
│   ├── email.py            # EmailSender abstraction (dev: logs; Phase 11: real provider)
│   ├── tokens.py           # issue + persist an access/refresh token pair
│   ├── anthropic_client.py # shared Claude client construction (Phase 2/4/5)
│   ├── legal_classifier.py # Claude: category + jurisdiction + risk classification (Phase 2/5)
│   ├── risk_engine.py      # risk_level -> advocate-recommendation decision (Phase 5)
│   ├── llm.py              # Claude: grounded answer generation (Phase 4)
│   ├── ingestion/          # fetch/extract/clean/chunk/embed/search (Phase 3)
│   └── rag/                # hybrid search + Reciprocal Rank Fusion (Phase 4)
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
            ├── chat.py       # send message (anon or logged in), list/get conversations
            └── legal_sources.py  # ingest/list/get/delete/reindex/search (RBAC)
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

## Chat (Phase 2) + grounded retrieval (Phase 4) + risk routing (Phase 5)

`POST /api/v1/chat/messages` works with or without a bearer token (public
tier). One Claude call classifies the message
(`app/services/legal_classifier.py::classify_query` — legal category,
jurisdiction scope, **risk level** LOW/MEDIUM/HIGH/CRITICAL, in/out of
scope — all four in the same forced tool call, see
[`docs/adr/0008-risk-scoring.md`](../../docs/adr/0008-risk-scoring.md)). If in
scope, `app/services/rag/retrieval.py::hybrid_search` retrieves candidate
`legal_chunks` (pgvector cosine similarity + Postgres full-text search, fused
with Reciprocal Rank Fusion); a second Claude call
(`app/services/llm.py::generate_grounded_answer`) answers using only those
chunks and cites them. If retrieval finds nothing — empty corpus, an
unrelated question, or `GEMINI_API_KEY` not configured — the endpoint returns
`INSUFFICIENT_EVIDENCE_MESSAGE` without calling Claude a second time, per the
platform's "grounded, not guessed" rule. See
[`docs/adr/0007-hybrid-search-and-grounding.md`](../../docs/adr/0007-hybrid-search-and-grounding.md).
Either way, a HIGH/CRITICAL risk level
(`app/services/risk_engine.py::requires_advocate_recommendation`) appends
`ADVOCATE_RECOMMENDATION_MESSAGE` to the reply.

Requires `ANTHROPIC_API_KEY` in `apps/api/.env` — unset by default. Without
it the endpoint returns `503 {"error": {"code": "llm_not_configured"}}`
rather than failing silently or guessing. `GEMINI_API_KEY` is also required
for grounded answers (see the knowledge-base section below) — its absence
degrades to the insufficient-evidence reply rather than a 503, since from the
user's side that's indistinguishable from "no matching sources exist".

## Legal knowledge base / ingestion (Phase 3)

`app/services/ingestion/` — fetch (HTTP) → extract (PDF/HTML) → clean →
chunk (size-based sliding window) → embed (Gemini) → persist (pgvector).
Driven by `/api/v1/admin/legal-sources/*` (RBAC — ADMIN/LEGAL_ADMIN):

| Method & path                              | Does |
| ------------------------------------------- | ---- |
| `POST /admin/legal-sources`                 | Ingest a new source (runs synchronously) |
| `GET /admin/legal-sources`                  | List, filter by `document_type`/`status` |
| `GET /admin/legal-sources/search?q=`        | Semantic search (pgvector cosine) |
| `GET /admin/legal-sources/{id}`             | Get one |
| `POST /admin/legal-sources/{id}/reindex`    | Re-fetch + re-chunk, replacing chunks |
| `DELETE /admin/legal-sources/{id}`          | Remove (cascades chunks) |

Ingestion failures (bad URL, extraction error, embeddings not configured) are
recorded on the `LegalDocument` row (`ingestion_status=FAILED`,
`ingestion_error=...`) rather than raised — see it via `GET .../{id}`.

Requires `GEMINI_API_KEY` in `apps/api/.env` (Google AI Studio, free tier) —
unset by default, same pattern as `ANTHROPIC_API_KEY`. `section`/`article`
chunk metadata is not populated yet (dropped as unreliable against real
PDF-extracted text — see
[`docs/adr/0006-chunking-strategy.md`](../../docs/adr/0006-chunking-strategy.md)).

## Migrations (Alembic)

```bash
uv run alembic upgrade head                       # apply
uv run alembic revision --autogenerate -m "add users"   # create
uv run alembic downgrade -1                        # roll back one
```

Alembic reads `DATABASE_URL_SYNC` (psycopg driver). Autogenerate compares
`app.db.base.Base.metadata` against the live DB, so every model module must be
imported in `app/models/__init__.py`. Hand-written migrations that use a
Postgres native enum (`user_role`, `verification_status`, `message_role`,
`legal_document_type`, `ingestion_status`) follow the `create_type=False` +
explicit `.create()`/`.drop()` pattern — see
`migrations/versions/20260102_0000-0002_auth_tables.py`. The `legal_chunks`
table adds a `pgvector` column (`Vector(768)`, from the `pgvector` package)
plus a raw-SQL HNSW cosine index — see
`migrations/versions/20260104_0000-0004_legal_sources.py`. Migration
`20260105_0000-0005_rag_grounding.py` adds a Postgres generated
`tsvector` column (`legal_chunks.content_tsv`, GIN-indexed) backing the
keyword half of hybrid search, plus `chat_messages.sources` (JSONB).
`20260106_0000-0006_risk_level.py` adds `chat_messages.risk_level` (indexed).

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
