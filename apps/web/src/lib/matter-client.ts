import type { MatterServiceType, MatterStatus } from '@legal-platform/shared';
import { apiFetch } from './api-client';

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
};
