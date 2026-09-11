# infrastructure/deployment

Targets and configuration for non-local environments. Phase 15 fills in the
actual pipelines; this directory holds the contract now so app code can be
written environment-aware from the start.

## Environments

| Env         | Frontend            | API                     | Postgres + pgvector | Redis            |
| ----------- | ------------------- | ----------------------- | ------------------- | --------------- |
| development | local `next dev`    | local `uvicorn` / Docker | Docker Compose      | Docker Compose  |
| staging     | Vercel (preview)    | container host          | **Supabase** (staging project) | managed Redis |
| production  | Vercel (production) | container host          | **Supabase** (prod project)    | managed Redis |

Decision record: [`docs/adr/0002-database-provisioning.md`](../../docs/adr/0002-database-provisioning.md).

## Config

- `staging.env.example` / `production.env.example` — the variable set each
  environment needs. Real values live in the deployment platform's secret
  store, never in this repo.
- The API reads the same `Settings` model everywhere (`apps/api/app/core/config.py`);
  only `APP_ENV`, the datastore URLs and secrets change between environments.

## Migrations against Supabase

Alembic is datastore-agnostic. Point `DATABASE_URL_SYNC` at the Supabase
connection string (session pooler, port 5432) and run:

```bash
cd apps/api && uv run alembic upgrade head
```

Run this as a release step before the new API image starts taking traffic.

## Still to define (Phase 15)

- Container host + image registry, deploy workflow, rollback
- Vercel project linking + preview/prod env wiring
- Managed Redis provider
- Object storage bucket + credentials
- Monitoring / error tracking / uptime checks
- Backup schedule + restore drills
