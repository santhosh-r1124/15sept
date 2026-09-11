# 0002 — Database provisioning

- Status: Accepted
- Date: 2026-09-10
- Deciders: Platform team

## Context

We need PostgreSQL with `pgvector` for relational data + embeddings, and Redis
for cache/sessions. Requirements: fully offline-capable local development, low
operational burden in staging/production, and a smooth path to a managed
service (roadmap Phase 15 calls for "Managed PostgreSQL").

## Decision

- **Local development**: self-hosted via Docker Compose
  (`infrastructure/docker/docker-compose.yml`) — `pgvector/pgvector:pg16` and
  `redis:7-alpine`. No cloud dependency to write code.
- **Staging & production**: **Supabase** managed Postgres (separate projects per
  environment) for `pgvector` support, backups and pooling out of the box;
  managed Redis alongside.
- Application config is environment-driven (`DATABASE_URL`, `DATABASE_URL_SYNC`,
  `REDIS_URL`); nothing about the datastore is hard-coded.

## Consequences

- Alembic migrations must stay datastore-agnostic (they are — plain SQL/DDL) so
  the same migration history applies to Compose Postgres and Supabase.
- Migrations run against Supabase as a release step (`alembic upgrade head` with
  `DATABASE_URL_SYNC` pointed at the Supabase session pooler, port 5432).
- Extensions (`vector`, `pgcrypto`, `pg_trgm`) are created **both** by a
  Compose init script and idempotently by migration `0001`, so a managed DB
  without init-script access still converges.
- Two sources of truth for "is the DB up": local Compose healthcheck vs Supabase
  status — the `/health/ready` probe abstracts this for the app.

## Alternatives considered

- **Supabase for local dev too** — removes Docker but requires network + shared
  cloud state; rejected for dev ergonomics.
- **Self-hosted Postgres in prod** (RDS-style or own VM) — more control, more
  ops; revisit if Supabase limits bite.
- **Separate vector DB** (e.g. a dedicated service) — extra moving part; pgvector
  is sufficient at expected scale and keeps joins local.
