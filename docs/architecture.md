# Architecture

Status: **Phase 0** — foundation skeleton. This document describes the target
shape; components fill in over later phases.

## 1. System overview

```
                         ┌───────────────┐
   Browser  ────────────▶│  Cloudflare   │   (prod: DNS, TLS, WAF, CDN)
                         └───────┬───────┘
                                 ▼
              ┌──────────────────────────────────┐
              │  Next.js  (apps/web)             │  consumer app
              │  Next.js  (apps/advocate-portal) │  advocate dashboard
              └───────────────┬──────────────────┘
                              │  HTTPS  (NEXT_PUBLIC_API_BASE_URL)
                              ▼
              ┌──────────────────────────────────┐
              │  FastAPI  (apps/api)             │
              │  ├─ /health, /health/ready       │
              │  ├─ /api/v1/*  (versioned)       │
              │  ├─ RequestContext middleware    │  request-id, access log
              │  ├─ structured logging (structlog)│
              │  └─ error envelope (AppError)    │
              └───────┬───────────────┬──────────┘
                      ▼               ▼
             ┌────────────────┐  ┌─────────┐
             │ PostgreSQL 16  │  │ Redis 7 │
             │ + pgvector     │  └─────────┘
             │ + pg_trgm      │
             └────────┬───────┘
                      ▼
             ┌────────────────────────────────────────────┐
             │ services/ (imported by apps/api)           │
             │  document-processing · rag · legal-classifier│
             │  risk-engine · notifications               │
             └───────────────┬────────────────────────────┘
                             ▼
                    Anthropic Claude  +  verified Indian legal sources
```

## 2. Request/response flow (from Phase 4)

```
query
  → legal domain classification        (services/legal-classifier)
  → Indian jurisdiction detection
  → query rewriting
  → hybrid search  (keyword via pg_trgm  +  vector via pgvector)
  → reranking
  → context selection
  → Claude
  → legal guardrails                   (services/risk-engine + rules)
  → answer + citations   (or INSUFFICIENT_EVIDENCE_MESSAGE)
```

## 3. Repository layout

See the table in the root [`README.md`](../README.md#monorepo-layout). Principles:

- **`apps/`** are deployable units (two Next.js apps, one FastAPI app).
- **`services/`** are Python libraries with domain logic, imported by `apps/api`.
  Promoted to standalone network services only if load or isolation demands it.
- **`packages/`** are shared TypeScript: `shared` (enums/contracts), `auth`
  (token types/helpers), `database` (Node DB client), `eslint-config`.
- The database schema lives in **`apps/api`** (SQLAlchemy + Alembic). Everything
  else consumes it.

## 4. Tech stack & rationale

| Concern       | Choice                        | Why                                                             |
| ------------- | ----------------------------- | ------------------------------------------------------------- |
| Frontend      | Next.js 15 / React 19         | App Router, RSC, first-class Vercel deploy, strong ecosystem   |
| Styling       | Tailwind CSS v4               | Fast iteration, no runtime cost                                |
| API           | FastAPI + Pydantic v2         | Async, typed, OpenAPI out of the box                          |
| ORM           | SQLAlchemy 2.0 (async)        | Mature, explicit, works with pgvector                          |
| Migrations    | Alembic                       | Autogenerate against ORM metadata; datastore-agnostic         |
| DB            | PostgreSQL + pgvector         | One store for relational + vector; `pg_trgm` for keyword search |
| Cache/queue   | Redis                         | Sessions, rate limits, job signalling                         |
| LLM           | Anthropic Claude              | Grounded generation with strong instruction-following         |
| Logging       | structlog                     | Structured, contextual (request-id), console↔JSON by env      |
| JS monorepo   | pnpm + Turborepo              | Efficient installs, cached task graph                         |
| Python deps   | uv                            | Fast, reproducible, lockfile-first                            |

Decision records: [`adr/`](adr/).

## 5. Cross-cutting conventions

- **Config**: one `Settings` object (`apps/api/app/core/config.py`); no direct
  `os.environ` reads. Frontends validate public env with zod (`src/lib/env.ts`).
- **Errors**: every non-2xx API response is `{ error: { code, message, details?,
  request_id } }` — typed in `@legal-platform/shared` as `ApiError`.
- **Correlation**: `X-Request-ID` accepted or generated per request, echoed in
  the response header and attached to every log line.
- **Health**: `/health` (liveness, no deps) vs `/health/ready` (checks Postgres +
  Redis, 503 when unhealthy).
- **Environments**: `development` (Docker Compose) · `staging` / `production`
  (Supabase Postgres, managed Redis). See [`environments.md`](environments.md).

## 6. Security posture (hardened in Phase 13)

RBAC · TLS everywhere · secure sessions · API rate limiting · input validation ·
prompt-injection defence · uploaded-file scanning · audit logs · secrets in a
managed store · tenant isolation for enterprise. Product safeguards: visible AI
disclaimer, advocate escalation, real citations only, jurisdiction awareness, no
attorney-client-relationship claims, user consent + privacy controls.
