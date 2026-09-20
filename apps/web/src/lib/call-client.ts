import type { CallSession, CallStatus } from '@legal-platform/shared';
import { apiFetch } from './api-client';
import { env } from './env';

const room = (matterId: string) => `/api/v1/matters/${matterId}/call`;

/** Bindings for the consultation-call endpoints (`/api/v1/matters/{id}/call*`). */
export const callClient = {
  status: (matterId: string, token: string) => apiFetch<CallStatus>(room(matterId), { token }),

  /** A one-minute ticket for the signaling socket, plus the ICE servers to use. */
  session: (matterId: string, token: string) =>
    apiFetch<CallSession>(`${room(matterId)}/session`, { method: 'POST', token }),
};

/** ws(s):// URL for a session, on the API's origin. The ticket is the only credential in it. */
export function socketUrl(session: CallSession): string {
  const url = new URL(env.NEXT_PUBLIC_API_BASE_URL);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = session.ws_path;
  url.search = `?ticket=${encodeURIComponent(session.ticket)}`;
  return url.toString();
}
