import { afterEach, describe, expect, it, vi } from 'vitest';
import { authClient } from './auth-client';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('authClient', () => {
  it('register posts to /api/v1/auth/register with the payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ access_token: 'a', refresh_token: 'r', token_type: 'bearer', expires_in: 1800 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await authClient.register({ email: 'a@b.test', password: 'password123' });

    expect(result.access_token).toBe('a');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/auth/register');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ email: 'a@b.test', password: 'password123' });
  });

  it('me() attaches an Authorization bearer header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: '1',
        email: 'a@b.test',
        role: 'CONSUMER',
        email_verified: false,
        is_active: true,
        display_name: null,
        state_code: null,
        preferred_language: null,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await authClient.me('the-access-token');

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer the-access-token');
  });

  it('resetPassword sends token and new_password', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ message: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);

    await authClient.resetPassword('tok', 'brand-new-password');

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      token: 'tok',
      new_password: 'brand-new-password',
    });
  });
});
