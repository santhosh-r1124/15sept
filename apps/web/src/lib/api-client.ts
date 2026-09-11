import { isApiError, type LivenessResponse, type ReadinessResponse } from '@legal-platform/shared';
import { env } from './env';

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Abort the request after this many ms (default 10_000). */
  timeoutMs?: number;
}

/**
 * Thin typed fetch wrapper around the FastAPI backend. Parses the shared error
 * envelope into {@link ApiRequestError}.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, timeoutMs = 10_000, headers, ...rest } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    clearTimeout(timer);
    throw new ApiRequestError(0, 'network_error', 'Could not reach the API.');
  }
  clearTimeout(timer);

  const payload = response.status === 204 ? null : await response.json().catch(() => null);

  if (!response.ok) {
    if (isApiError(payload)) {
      throw new ApiRequestError(
        response.status,
        payload.error.code,
        payload.error.message,
        payload.error.request_id,
      );
    }
    throw new ApiRequestError(response.status, 'http_error', `Request failed (${response.status}).`);
  }

  return payload as T;
}

export const api = {
  liveness: () => apiFetch<LivenessResponse>('/health'),
  readiness: () => apiFetch<ReadinessResponse>('/health/ready'),
  meta: () => apiFetch<{ name: string; version: string; environment: string }>('/api/v1/meta'),
};
