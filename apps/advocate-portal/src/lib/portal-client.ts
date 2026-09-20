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
  /** Decimal serialised as a string by Pydantic, e.g. "600.00". */
  quoted_fee: string | null;
  decision_note: string | null;
  scheduled_at: string | null;
  paid_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  advocate: { profile_id: string; display_name: string | null };
  /** No email on purpose: FRD 10 shows the advocate an "anonymous/verified" client, not contact details. */
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

export interface EarningsSummary {
  currency: string;
  gross_earned: string;
  platform_fee_percent: string;
  platform_fee: string;
  net_earned: string;
  pending: string;
}

export interface UpcomingAppointment {
  matter_id: string;
  title: string;
  scheduled_at: string;
  consultation_minutes: number | null;
  client_name: string | null;
}

export interface AdvocateDashboard {
  new_requests: number;
  awaiting_payment: number;
  to_schedule: number;
  open_document_requests: number;
  awaiting_reply: number;
  upcoming_appointments: UpcomingAppointment[];
  earnings: EarningsSummary;
}

export interface EarningsLineItem {
  matter_id: string;
  title: string;
  amount: string;
  refunded: string;
  status: MatterStatus;
  paid_at: string | null;
  closed_at: string | null;
}

export interface EarningsOut {
  summary: EarningsSummary;
  items: EarningsLineItem[];
}

export interface RefundOut {
  id: string;
  amount: string;
  reason: string;
  created_at: string;
}

export interface PaymentOut {
  id: string;
  matter_id: string;
  amount: string;
  refunded_amount: string;
  currency: string;
  status: 'SUCCEEDED' | 'PARTIALLY_REFUNDED' | 'REFUNDED';
  provider: string;
  created_at: string;
  refunds: RefundOut[];
}

export interface InvoiceOut {
  id: string;
  invoice_number: string;
  matter_id: string;
  description: string;
  client_name: string;
  advocate_name: string;
  amount: string;
  refunded_amount: string;
  currency: string;
  issued_at: string;
}

export interface MatterPaymentOut {
  payment: PaymentOut;
  invoice: InvoiceOut;
}

export interface PaymentSummaryOut {
  payment_id: string;
  matter_id: string;
  matter_title: string;
  invoice_id: string;
  invoice_number: string;
  amount: string;
  refunded_amount: string;
  currency: string;
  status: 'SUCCEEDED' | 'PARTIALLY_REFUNDED' | 'REFUNDED';
  created_at: string;
}

export interface PaginatedPayments {
  items: PaymentSummaryOut[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Invoices are HTML pages served by the API. Fetched with the Bearer header and opened from a
 * blob URL - which, unlike the HTTP response, carries no Content-Security-Policy header - so the
 * same lock-down is injected as a <meta> tag before it is opened.
 */
const INVOICE_CSP =
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">';

async function failFrom(response: Response): Promise<never> {
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
  if (!response.ok) await failFrom(response);
  return response;
}

const m = (id: string) => `/api/v1/matters/${id}`;

/** Bindings for the advocate's side of `/api/v1/matters/*` and `/api/v1/advocates/me/*`. */
export const portalClient = {
  dashboard: (token: string) =>
    apiFetch<AdvocateDashboard>('/api/v1/advocates/me/dashboard', { token }),

  earnings: (token: string) => apiFetch<EarningsOut>('/api/v1/advocates/me/earnings', { token }),

  listMatters: (token: string, status?: MatterStatus) =>
    apiFetch<PaginatedMatters>(`/api/v1/matters?limit=100${status ? `&status=${status}` : ''}`, {
      token,
    }),

  getMatter: (id: string, token: string) => apiFetch<MatterOut>(m(id), { token }),

  act: (
    id: string,
    action: 'accept' | 'reject' | 'cancel' | 'schedule' | 'close',
    token: string,
    body: Record<string, unknown> = {},
  ) => apiFetch<MatterOut>(`${m(id)}/${action}`, { method: 'POST', body, token }),

  messages: (id: string, token: string) =>
    apiFetch<MatterMessageOut[]>(`${m(id)}/messages`, { token }),

  postMessage: (id: string, body: string, token: string) =>
    apiFetch<MatterMessageOut>(`${m(id)}/messages`, { method: 'POST', body: { body }, token }),

  documents: (id: string, token: string) =>
    apiFetch<MatterDocumentsOut>(`${m(id)}/documents`, { token }),

  requestDocument: (id: string, description: string, token: string) =>
    apiFetch<DocumentRequestOut>(`${m(id)}/document-requests`, {
      method: 'POST',
      body: { description },
      token,
    }),

  /** Multipart upload; the browser sets the Content-Type boundary, so no JSON header here. */
  async uploadFile(
    id: string,
    file: File,
    token: string,
    opts: { requestId?: string; isFinal?: boolean } = {},
  ): Promise<MatterFileOut> {
    const form = new FormData();
    form.set('file', file);
    if (opts.requestId) form.set('request_id', opts.requestId);
    if (opts.isFinal) form.set('is_final', 'true');
    const response = await authedRaw(`${m(id)}/files`, token, { method: 'POST', body: form });
    return (await response.json()) as MatterFileOut;
  },

  /** Downloads need the Bearer header, so a plain <a href> can't be used: fetch, then save the blob. */
  async downloadFile(id: string, file: MatterFileOut, token: string): Promise<void> {
    const response = await authedRaw(`${m(id)}/files/${file.id}`, token);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = file.file_name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
  payment: (id: string, token: string) =>
    apiFetch<MatterPaymentOut>(`/api/v1/payments/matters/${id}`, { token }),

  listPayments: (token: string) =>
    apiFetch<PaginatedPayments>('/api/v1/payments/mine?limit=100', { token }),

  async openInvoice(invoiceId: string, token: string): Promise<void> {
    const response = await authedRaw(`/api/v1/payments/invoices/${invoiceId}/html`, token);
    const html = (await response.text()).replace('<head>', `<head>${INVOICE_CSP}`);
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    window.open(url, '_blank', 'noopener');
  },
};
