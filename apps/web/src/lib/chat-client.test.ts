import { afterEach, describe, expect, it, vi } from 'vitest';
import { chatClient } from './chat-client';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('chatClient', () => {
  it('sendMessage posts message + conversation_id and omits auth when anonymous', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        conversation_id: 'c1',
        user_message: {
          id: 'm1',
          role: 'user',
          content: 'hi',
          legal_category: null,
          jurisdiction_scope: null,
          is_out_of_scope: null,
          created_at: '2026-01-01T00:00:00Z',
        },
        assistant_message: {
          id: 'm2',
          role: 'assistant',
          content: 'hello',
          legal_category: null,
          jurisdiction_scope: null,
          is_out_of_scope: null,
          created_at: '2026-01-01T00:00:01Z',
        },
        disclaimer: 'General information only.',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await chatClient.sendMessage('hi', null, null);

    expect(result.conversation_id).toBe('c1');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/chat/messages');
    expect(JSON.parse(init.body as string)).toEqual({ message: 'hi', conversation_id: undefined });
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBeNull();
  });

  it('sendMessage attaches conversation_id and bearer token when present', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        conversation_id: 'c1',
        user_message: {
          id: 'm1',
          role: 'user',
          content: 'hi',
          legal_category: null,
          jurisdiction_scope: null,
          is_out_of_scope: null,
          created_at: '2026-01-01T00:00:00Z',
        },
        assistant_message: {
          id: 'm2',
          role: 'assistant',
          content: 'hello',
          legal_category: null,
          jurisdiction_scope: null,
          is_out_of_scope: null,
          created_at: '2026-01-01T00:00:01Z',
        },
        disclaimer: 'General information only.',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await chatClient.sendMessage('follow-up', 'c1', 'the-token');

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      message: 'follow-up',
      conversation_id: 'c1',
    });
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer the-token');
  });

  it('listConversations requires a token and hits the right endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    await chatClient.listConversations('the-token');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/chat/conversations');
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer the-token');
  });
});
