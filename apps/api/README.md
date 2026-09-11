# legal-platform-api

FastAPI backend for the Indian Legal Advisor platform.

## Layout

```
app/
├── main.py              # app factory, middleware, lifespan, exception handlers
├── core/
│   ├── config.py        # pydantic-settings — typed env config + Environment
│   ├── logging.py       # structlog setup (console dev / JSON prod)
│   └── errors.py        # AppError hierarchy + handlers + error envelope
├── db/
│   ├── base.py          # SQLAlchemy DeclarativeBase + naming convention
│   └── session.py       # async engine + sessionmaker lifecycle
├── models/              # ORM models (populated from Phase 1)
├── middleware/
│   └── request_context.py  # request-id, structured access log, timing
├── services/
│   └── redis.py         # async Redis client lifecycle
└── api/
    ├── deps.py          # FastAPI dependencies (get_db, get_redis)
    └── v1/
        ├── router.py    # /api/v1 aggregate router
        └── routes/
            ├── health.py  # /health, /health/ready
            └── meta.py    # /api/v1/meta
```

## Develop

```bash
uv sync                                   # create .venv, install deps
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs>.

## Migrations (Alembic)

```bash
uv run alembic upgrade head                       # apply
uv run alembic revision --autogenerate -m "add users"   # create
uv run alembic downgrade -1                        # roll back one
```

Alembic reads `DATABASE_URL_SYNC` (psycopg driver). Autogenerate compares
`app.db.base.Base.metadata` against the live DB, so every model module must be
imported in `app/models/__init__.py`.

## Quality gates

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest --cov
```
