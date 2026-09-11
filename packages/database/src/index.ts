/**
 * @legal-platform/database — a thin, typed PostgreSQL client for Node consumers
 * (scripts, seeders, Next.js route handlers that need direct DB access).
 *
 * The **schema is owned by `apps/api`** (SQLAlchemy models + Alembic migrations).
 * The `Database` type in `./types.ts` is regenerated from the migrated schema —
 * see this package's README. Application code should prefer calling the FastAPI
 * backend over querying the database directly.
 */

export { createDbClient, type DbClient, type DbClientOptions } from './client';
export type { Database } from './types';
