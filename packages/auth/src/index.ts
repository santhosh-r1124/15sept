/**
 * @legal-platform/auth — shared authentication types and lightweight,
 * dependency-free helpers used by both frontends.
 *
 * Token *issuance and verification* is performed by `apps/api` (Phase 1).
 * This package only models the shapes and parses headers/claims client-side.
 */

export * from './types';
export * from './token';
