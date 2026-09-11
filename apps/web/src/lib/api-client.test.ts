import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError, apiFetch } from './api-client';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('apiFetch', () => {
  it('returns parsed JSON on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
    await expect(apiFetch('/health')).resolves.toEqual({ status: 'ok' });
  });

  it('maps the shared error envelope to ApiRequestError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: 'not_found', message: 'nope', request_id: 'abc' },
          }),
          { status: 404, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );
    await expect(apiFetch('/x')).rejects.toMatchObject({
      name: 'ApiRequestError',
      status: 404,
      code: 'not_found',
      requestId: 'abc',
    });
  });

  it('raises a network_error when fetch throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('boom')));
    await expect(apiFetch('/x')).rejects.toBeInstanceOf(ApiRequestError);
  });
});
