import { isApiError, type MatterServiceType, type MatterStatus } from '@legal-platform/shared';
import { ApiRequestError, apiFetch } from './api-client';
import { env } from './env';

export interface MatterOut {
  id: string;
  service_type: MatterServiceType;
  consultation_minutes: number | null;
  title: string;
  requirement: string;
  preferred_language: string | null;
  status: MatterStatus;
  /** Decimal, serialised as a string by Pydantic (e.g. "600.00"). */
  quoted_fee: string | null;
  decision_note: string | null;
  scheduled_at: string | null;
  paid_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  advocate: { profile_id: string; display_name: string | null };
  consumer: { display_name: string | null; verified: boolean };
}

export interface PaginatedMatters {
  items: MatterOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface MatterMessageOut {
  id: string;
  matter_id: string;
  sender_id: string;
  sender_role: 'CONSUMER' | 'ADVOCATE';
  body: string;
  created_at: string;
}

export interface DocumentRequestOut {
  id: string;
  matter_id: string;
  description: string;
  status: 'OPEN' | 'FULFILLED';
  created_at: string;
}

export interface MatterFileOut {
  id: string;
  matter_id: string;
  request_id: string | null;
  file_name: string;
  content_type: string;
  size_bytes: number;
  is_final: boolean;
  uploader_role: 'CONSUMER' | 'ADVOCATE';
  created_at: string;
}

export interface MatterDocumentsOut {
  requests: DocumentRequestOut[];
  files: MatterFileOut[];
}

/** fetch() with the Bearer header, turning the API's error envelope into an ApiRequestError. */
async function authedRaw(path: string, token: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, ...init.headers },
    });
  } catch {
    throw new ApiRequestError(0, 'network_error', 'Could not reach the API.');
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
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
  return response;
}

export interface CreateMatterPayload {
  advocate_id: string;
  service_type: MatterServiceType;
  consultation_minutes?: number;
  title: string;
  requirement: string;
  preferred_language?: string;
}

/** Bindings for `/api/v1/matters/*`. Every call needs a signed-in user. */
export const matterClient = {
  create: (payload: CreateMatterPayload, token: string) =>
    apiFetch<MatterOut>('/api/v1/matters', { method: 'POST', body: payload, token }),

  list: (token: string, status?: MatterStatus) =>
    apiFetch<PaginatedMatters>(`/api/v1/matters${status ? `?status=${status}` : ''}`, { token }),

  get: (id: string, token: string) => apiFetch<MatterOut>(`/api/v1/matters/${id}`, { token }),

  act: (
    id: string,
    action: 'accept' | 'reject' | 'cancel' | 'pay' | 'schedule' | 'close',
    token: string,
    body: Record<string, unknown> = {},
  ) => apiFetch<MatterOut>(`/api/v1/matters/${id}/${action}`, { method: 'POST', body, token }),

  messages: (id: string, token: string) =>
    apiFetch<MatterMessageOut[]>(`/api/v1/matters/${id}/messages`, { token }),

  postMessage: (id: string, body: string, token: string) =>
    apiFetch<MatterMessageOut>(`/api/v1/matters/${id}/messages`, {
      method: 'POST',
      body: { body },
      token,
    }),

  documents: (id: string, token: string) =>
    apiFetch<MatterDocumentsOut>(`/api/v1/matters/${id}/documents`, { token }),

  /** Multipart upload; the browser sets the Content-Type boundary, so no JSON header here. */
  async uploadFile(
    id: string,
    file: File,
    token: string,
    opts: { requestId?: string } = {},
  ): Promise<MatterFileOut> {
    const form = new FormData();
    form.set('file', file);
    if (opts.requestId) form.set('request_id', opts.requestId);
    const response = await authedRaw(`/api/v1/matters/${id}/files`, token, {
      method: 'POST',
      body: form,
    });
    return (await response.json()) as MatterFileOut;
  },

  /** Downloads need the Bearer header, so fetch the bytes and save the blob. */
  async downloadFile(id: string, file: MatterFileOut, token: string): Promise<void> {
    const response = await authedRaw(`/api/v1/matters/${id}/files/${file.id}`, token);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = file.file_name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
