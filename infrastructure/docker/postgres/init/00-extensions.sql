-- Runs once, on first initialisation of the postgres data volume.
-- Alembic migration 0001 also creates these (idempotently) so a Supabase or
-- managed database without init-script access still ends up correct — this file
-- just makes a fresh local database usable before migrations run.
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
