import type { Role } from '@legal-platform/shared';

/** Authenticated principal as surfaced to the frontends by `apps/api`. */
export interface AuthUser {
  id: string;
  email: string;
  role: Role;
  emailVerified: boolean;
  displayName: string | null;
  /** ISO-3166-2:IN state code, when known. */
  stateCode: string | null;
  preferredLanguage: string | null;
}

/** Access + refresh token pair returned by the login / refresh endpoints. */
export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  tokenType: 'Bearer';
  expiresIn: number;
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
}
