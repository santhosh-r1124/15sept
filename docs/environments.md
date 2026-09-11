# Environments

Three environments, one codebase. `APP_ENV` (`NEXT_PUBLIC_APP_ENV` on the
frontends) selects behaviour; only datastore URLs and secrets differ.

| | development | staging | production |
| --- | --- | --- | --- |
| `APP_ENV` | `development` | `staging` | `production` |
| Frontends | `next dev` (local) | Vercel preview | Vercel production |
| API | `uvicorn` local or Docker Compose | container host | container host |
| Postgres + pgvector | Docker Compose (`pgvector/pgvector:pg16`) | Supabase (staging project) | Supabase (prod project) |
| Redis | Docker Compose (`redis:7`) | managed | managed |
| Logging | `console`, `DEBUG` | `json`, `INFO` | `json`, `INFO` |
| API docs (`/docs`) | enabled | enabled | **disabled** |
| Object storage | — (Phase 6+) | bucket | bucket |

## Local (development)

```bash
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
cp apps/advocate-portal/.env.example apps/advocate-portal/.env.local

pnpm install
pnpm stack:up          # postgres + redis + api  (Docker)
pnpm db:migrate        # alembic upgrade head
pnpm --filter @legal-platform/web dev
pnpm --filter @legal-platform/advocate-portal dev
```

Full stack in Docker (adds the two Next apps):

```bash
docker compose -f infrastructure/docker/docker-compose.yml --project-directory . --profile web up -d --build
```

## staging / production

Config template: `infrastructure/deployment/{staging,production}.env.example`.
Real values live in the deployment platform's secret store — never committed.

Release order:

1. Build + push the API image.
2. Run `alembic upgrade head` against the target Supabase database (release step,
   before traffic shift).
3. Roll the API.
4. Deploy the frontends (Vercel) with the matching `NEXT_PUBLIC_*` env.

Pipelines are defined in Phase 15; `docs/adr/0002-database-provisioning.md`
records the datastore decision.
