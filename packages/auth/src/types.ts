import type { Role } from '@legal-platform/shared';

/**
 * Authenticated principal as surfaced by `apps/api` (`GET /users/me`, and the
 * `token_pair` response after register/login). Field names are snake_case to
 * match the API wire format exactly — see `app/schemas/user.py::UserOut`.
 */
export interface AuthUser {
  id: string;
  email: string;
  role: Role;
  email_verified: boolean;
  is_active: boolean;
  display_name: string | null;
  /** ISO-3166-2:IN state code, when known. */
  state_code: string | null;
  preferred_language: string | null;
}

/**
 * Access + refresh token pair returned by register/login/refresh.
 * See `app/schemas/auth.py::TokenPair`.
 */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

/** Decoded JWT claims (HS256). `sub` is the user id. */
export interface JwtClaims {
  sub: string;
  role: Role;
  /** issued-at, seconds since epoch */
  iat: number;
  /** expiry, seconds since epoch */
  exp: number;
  /** token kind — access tokens only are accepted for API calls */
  typ: 'access' | 'refresh';
  /** present on refresh tokens only */
  jti?: string;
}
