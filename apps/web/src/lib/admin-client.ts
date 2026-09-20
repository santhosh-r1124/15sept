import type {
  MatterServiceType,
  MatterStatus,
  Role,
  VerificationStatus,
} from '@legal-platform/shared';
import { apiFetch } from './api-client';
import type { PaymentOut, PaymentSummaryOut } from './matter-client';

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Overview {
  users_by_role: Record<string, number>;
  advocates_by_status: Record<string, number>;
  matters_by_status: Record<string, number>;
  sources_by_status: Record<string, number>;
  payments: { count: number; gross: string; refunded: string };
  advocates_pending: number;
  reviews_pending: number;
  emails_pending: number;
  emails_failed: number;
}

export interface AdminUserRow {
  id: string;
  email: string;
  role: Role;
  email_verified: boolean;
  is_active: boolean;
  display_name: string | null;
  state_code: string | null;
  preferred_language: string | null;
}

export interface AdminAdvocate {
  id: string;
  user_id: string;
  display_name: string | null;
  email: string;
  practice_areas: string[];
  state_code: string;
  city: string;
  languages: string[];
  consultation_fee: string | null;
  bio: string | null;
  experience_years: number | null;
  verification_status: VerificationStatus;
  verification_note: string | null;
  created_at: string;
}

export interface AdminMatter {
  id: string;
  title: string;
  service_type: MatterServiceType;
  status: MatterStatus;
  quoted_fee: string | null;
  consumer_name: string | null;
  advocate_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueryReview {
  id: string;
  conversation_id: string;
  created_at: string;
  risk_level: 'HIGH' | 'CRITICAL';
  legal_category: string | null;
  jurisdiction_scope: string | null;
  question: string;
  answer: string | null;
  answer_source_count: number | null;
  /** Whether a logged-in user asked. Never who: reviewers don't see identities. */
  registered: boolean;
  reviewed_at: string | null;
  review_note: string | null;
}

export type SourceStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export interface LegalSource {
  id: string;
  title: string;
  law_name: string | null;
  jurisdiction: string;
  state_code: string | null;
  source_url: string;
  document_type: string;
  effective_date: string | null;
  version: string | null;
  ingestion_status: SourceStatus;
  ingestion_error: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface NewSource {
  title: string;
  source_url: string;
  document_type: string;
  law_name?: string;
  jurisdiction?: string;
  state_code?: string;
  version?: string;
}

/** Fetching / re-indexing a source runs synchronously on the server and can take a while. */
const INGEST_TIMEOUT_MS = 180_000;

const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
};

/** Bindings for the admin / legal-ops API (`/api/v1/admin/*`). All need an ADMIN token. */
export const adminClient = {
  overview: (token: string) => apiFetch<Overview>('/api/v1/admin/overview', { token }),

  users: (token: string, p: { q?: string; role?: string; limit?: number } = {}) =>
    apiFetch<Paginated<AdminUserRow>>(
      `/api/v1/admin/users${qs({ q: p.q, role: p.role, limit: p.limit ?? 50 })}`,
      { token },
    ),

  setUserActive: (id: string, isActive: boolean, token: string) =>
    apiFetch<AdminUserRow>(`/api/v1/admin/users/${id}`, {
      method: 'PATCH',
      body: { is_active: isActive },
      token,
    }),

  advocates: (token: string, p: { status?: string; limit?: number } = {}) =>
    apiFetch<Paginated<AdminAdvocate>>(
      `/api/v1/admin/advocates${qs({ status: p.status, limit: p.limit ?? 50 })}`,
      { token },
    ),

  verifyAdvocate: (profileId: string, note: string | undefined, token: string) =>
    apiFetch<unknown>(`/api/v1/admin/advocates/${profileId}/verify`, {
      method: 'POST',
      body: note ? { note } : {},
      token,
    }),

  rejectAdvocate: (profileId: string, note: string, token: string) =>
    apiFetch<unknown>(`/api/v1/admin/advocates/${profileId}/reject`, {
      method: 'POST',
      body: { note },
      token,
    }),

  reviews: (token: string, p: { status?: string; riskLevel?: string; limit?: number } = {}) =>
    apiFetch<Paginated<QueryReview>>(
      `/api/v1/admin/reviews${qs({ status: p.status, risk_level: p.riskLevel, limit: p.limit ?? 50 })}`,
      { token },
    ),

  reviewQuery: (id: string, note: string | undefined, token: string) =>
    apiFetch<QueryReview>(`/api/v1/admin/reviews/${id}/review`, {
      method: 'POST',
      body: note ? { note } : {},
      token,
    }),

  matters: (token: string, p: { status?: string; limit?: number } = {}) =>
    apiFetch<Paginated<AdminMatter>>(
      `/api/v1/admin/matters${qs({ status: p.status, limit: p.limit ?? 50 })}`,
      { token },
    ),

  payments: (token: string) =>
    apiFetch<Paginated<PaymentSummaryOut>>('/api/v1/admin/payments?limit=50', { token }),

  refund: (paymentId: string, amount: string | undefined, reason: string, token: string) =>
    apiFetch<PaymentOut>(`/api/v1/admin/payments/${paymentId}/refund`, {
      method: 'POST',
      body: { ...(amount ? { amount } : {}), reason },
      token,
    }),

  sources: (token: string) =>
    apiFetch<Paginated<LegalSource>>('/api/v1/admin/legal-sources?limit=100', { token }),

  createSource: (source: NewSource, token: string) =>
    apiFetch<LegalSource>('/api/v1/admin/legal-sources', {
      method: 'POST',
      body: source,
      token,
      timeoutMs: INGEST_TIMEOUT_MS,
    }),

  reindexSource: (id: string, token: string) =>
    apiFetch<LegalSource>(`/api/v1/admin/legal-sources/${id}/reindex`, {
      method: 'POST',
      token,
      timeoutMs: INGEST_TIMEOUT_MS,
    }),

  deleteSource: (id: string, token: string) =>
    apiFetch<void>(`/api/v1/admin/legal-sources/${id}`, { method: 'DELETE', token }),
};
