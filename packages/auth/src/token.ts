import type { JwtClaims } from './types';

/** Extract a bearer token from an `Authorization` header value. */
export function parseAuthHeader(header: string | null | undefined): string | null {
  if (!header) return null;
  const [scheme, value] = header.split(' ');
  if (scheme?.toLowerCase() !== 'bearer' || !value) return null;
  return value.trim();
}

function base64UrlDecode(segment: string): string {
  const padded = segment.replace(/-/g, '+').replace(/_/g, '/');
  const withPad = padded.padEnd(Math.ceil(padded.length / 4) * 4, '=');
  // `atob` is a global in browsers and in Node >= 18.
  return atob(withPad);
}

/**
 * Decode (NOT verify) a JWT payload. Signature verification happens server-side
 * in `apps/api`; this is only for reading non-sensitive claims like `exp` in the
 * browser to decide when to refresh.
 */
export function decodeJwtClaims(token: string): JwtClaims | null {
  const parts = token.split('.');
  if (parts.length !== 3 || !parts[1]) return null;
  try {
    const json = base64UrlDecode(parts[1]);
    const parsed = JSON.parse(json) as Partial<JwtClaims>;
    if (typeof parsed.sub !== 'string' || typeof parsed.exp !== 'number') return null;
    return parsed as JwtClaims;
  } catch {
    return null;
  }
}

/** True when the token is absent or past (or within `skewSeconds` of) expiry. */
export function isTokenExpired(token: string, skewSeconds = 30): boolean {
  const claims = decodeJwtClaims(token);
  if (!claims) return true;
  const now = Math.floor(Date.now() / 1000);
  return claims.exp - skewSeconds <= now;
}
