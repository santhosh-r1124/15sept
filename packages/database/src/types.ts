/**
 * Generated database types.
 *
 * PLACEHOLDER — regenerated from the live (migrated) schema once tables exist
 * (Phase 1+). Generation command lives in this package's README.
 * Until then this is an empty schema so downstream typechecks stay green.
 */
export interface Database {
  // e.g. users: { id: string; email: string; ... }
  [table: string]: Record<string, unknown>;
}
