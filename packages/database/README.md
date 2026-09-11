# @legal-platform/database

Thin, typed PostgreSQL client for **Node** consumers (scripts, seeders, the
occasional Next.js route handler that needs direct DB access).

## Schema ownership

The database schema is **owned by `apps/api`** — SQLAlchemy 2.0 models plus
Alembic migrations. This package does **not** define or migrate tables. See
[`docs/adr/0003-schema-and-migrations.md`](../../docs/adr/0003-schema-and-migrations.md).

## Usage

```ts
import { createDbClient } from '@legal-platform/database';

const sql = createDbClient(); // reads DATABASE_URL_TS / DATABASE_URL
const rows = await sql`select 1 as ok`;
await sql.end();
```

The app's `DATABASE_URL` uses a SQLAlchemy scheme (`postgresql+asyncpg://…`);
`createDbClient` strips the `+driver` suffix automatically. You can also set
`DATABASE_URL_TS` to a plain `postgresql://…` URL specifically for Node tools.

## Regenerating `src/types.ts`

Once tables exist (Phase 1+), regenerate types from the **migrated** local
database:

```bash
# 1. bring up the stack and migrate
pnpm stack:up && pnpm db:migrate

# 2. generate (kysely-codegen shown; swap for your preferred tool)
pnpm --filter @legal-platform/database exec \
  kysely-codegen --dialect postgres \
  --url "postgresql://legal:legal_dev_password@localhost:5432/legal_platform" \
  --out-file src/types.ts
```

Commit the regenerated file so typechecks are deterministic in CI.
