import { describe, expect, it } from 'vitest';
import { decodeJwtClaims, isTokenExpired, parseAuthHeader } from './token';

function makeToken(payload: Record<string, unknown>): string {
  const b64 = (obj: unknown) =>
    Buffer.from(JSON.stringify(obj))
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64(payload)}.signature`;
}

describe('parseAuthHeader', () => {
  it('extracts a bearer token', () => {
    expect(parseAuthHeader('Bearer abc.def.ghi')).toBe('abc.def.ghi');
  });
  it('rejects non-bearer or empty headers', () => {
    expect(parseAuthHeader('Basic xxx')).toBeNull();
    expect(parseAuthHeader(null)).toBeNull();
    expect(parseAuthHeader('Bearer')).toBeNull();
  });
});

describe('decodeJwtClaims / isTokenExpired', () => {
  it('decodes a well-formed payload', () => {
    const token = makeToken({ sub: 'u1', role: 'CONSUMER', iat: 1, exp: 9999999999, typ: 'access' });
    expect(decodeJwtClaims(token)?.sub).toBe('u1');
  });

  it('treats malformed tokens as expired', () => {
    expect(isTokenExpired('not-a-jwt')).toBe(true);
  });

  it('detects past expiry', () => {
    const token = makeToken({ sub: 'u1', exp: 1 });
    expect(isTokenExpired(token)).toBe(true);
  });
});
