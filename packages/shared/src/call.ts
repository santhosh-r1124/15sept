/**
 * Voice / video consultation contract: the JSON the signaling WebSocket carries and the REST
 * shapes around it. Mirrored by `apps/api` (`app/api/v1/routes/calls.py`, `app/schemas/call.py`).
 *
 * Media itself (WebRTC) never appears here: it flows browser to browser.
 */

export type CallRole = 'CONSUMER' | 'ADVOCATE';

/** Why the room can't be joined right now (`access.reason`). */
export const CALL_UNAVAILABLE_REASONS = [
  'not_a_consultation',
  'unpaid',
  'ended',
  'too_early',
  'window_passed',
] as const;
export type CallUnavailableReason = (typeof CALL_UNAVAILABLE_REASONS)[number];

/** `RTCIceCandidateInit` without depending on the DOM lib (this package has none). */
export interface IceCandidateJson {
  candidate: string;
  sdpMid?: string | null;
  sdpMLineIndex?: number | null;
  usernameFragment?: string | null;
}

/** What one browser sends the other through the server, verbatim. */
export type CallSignal =
  | { kind: 'offer'; sdp: string }
  | { kind: 'answer'; sdp: string }
  | { kind: 'candidate'; candidate: IceCandidateJson | null };

export type CallServerMessage =
  /** You are in the room. `peer_present`: the other person is already here. */
  | { type: 'joined'; role: CallRole; peer_present: boolean }
  /** The other person arrived and you were here first: create the offer. */
  | { type: 'peer-joined' }
  /** The other person left: drop the connection and wait for them to come back. */
  | { type: 'peer-left' }
  | { type: 'signal'; data: CallSignal }
  /** The booked window is over; the server is closing the socket. */
  | { type: 'ended'; reason: string }
  | { type: 'error'; code: string }
  | { type: 'pong' };

export type CallClientMessage =
  | { type: 'signal'; data: CallSignal }
  | { type: 'ping' }
  | { type: 'bye' };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isCallSignal(value: unknown): value is CallSignal {
  if (!isRecord(value)) return false;
  if (value.kind === 'offer' || value.kind === 'answer') return typeof value.sdp === 'string';
  if (value.kind === 'candidate') {
    return (
      value.candidate === null ||
      (isRecord(value.candidate) && typeof value.candidate.candidate === 'string')
    );
  }
  return false;
}

/** Parses one text frame from the server; `null` for anything that isn't a valid message. */
export function parseCallServerMessage(raw: string): CallServerMessage | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;
  switch (value.type) {
    case 'joined':
      return (value.role === 'CONSUMER' || value.role === 'ADVOCATE') &&
        typeof value.peer_present === 'boolean'
        ? { type: 'joined', role: value.role, peer_present: value.peer_present }
        : null;
    case 'peer-joined':
    case 'peer-left':
    case 'pong':
      return { type: value.type };
    case 'signal':
      return isCallSignal(value.data) ? { type: 'signal', data: value.data } : null;
    case 'ended':
      return { type: 'ended', reason: typeof value.reason === 'string' ? value.reason : 'ended' };
    case 'error':
      return { type: 'error', code: typeof value.code === 'string' ? value.code : 'error' };
    default:
      return null;
  }
}

/** WebSocket close codes the call endpoint uses (see `routes/calls.py`). */
export const CALL_CLOSE = {
  REPLACED: 4001,
  BAD_TICKET: 4401,
  NOT_ALLOWED: 4403,
  IDLE_OR_TIME_LIMIT: 4408,
  TOO_MANY_MESSAGES: 4429,
} as const;

export interface CallClose {
  /** Shown to the person. */
  message: string;
  /** Whether trying to reconnect (with a fresh ticket) could help. */
  retry: boolean;
}

/** What a socket close means for the person in the call. */
export function describeCallClose(code: number): CallClose {
  switch (code) {
    case CALL_CLOSE.REPLACED:
      return { message: 'You joined this consultation from another tab or device.', retry: false };
    case CALL_CLOSE.NOT_ALLOWED:
      return { message: 'You can’t join this consultation right now.', retry: false };
    case CALL_CLOSE.IDLE_OR_TIME_LIMIT:
      return { message: 'The consultation window has ended.', retry: false };
    case CALL_CLOSE.TOO_MANY_MESSAGES:
      return { message: 'The connection was closed after too much activity.', retry: false };
    case 1008:
      return { message: 'This page isn’t allowed to open the consultation.', retry: false };
    case 1000:
      return { message: 'The call ended.', retry: false };
    default:
      // 1006 (dropped), 1001 (going away), 4401 (ticket used up): a new ticket may work.
      return { message: 'The connection was lost.', retry: true };
  }
}

/** 75 -> "1:15", 3725 -> "1:02:05". */
export function formatCallDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  const two = (n: number) => String(n).padStart(2, '0');
  return hours > 0 ? `${hours}:${two(minutes)}:${two(seconds)}` : `${minutes}:${two(seconds)}`;
}

// ---- REST shapes ---------------------------------------------------------------------------

export interface CallAccess {
  allowed: boolean;
  reason: CallUnavailableReason | null;
  opens_at: string | null;
  closes_at: string | null;
}

export interface CallRecord {
  id: string;
  opened_by: CallRole;
  opened_at: string;
  connected_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  ended_reason: string | null;
}

export interface CallStatus {
  access: CallAccess;
  present: CallRole[];
  calls: CallRecord[];
}

export interface CallIceServer {
  urls: string | string[];
  username?: string;
  credential?: string;
}

export interface CallSession {
  ticket: string;
  expires_in: number;
  ws_path: string;
  role: CallRole;
  ice_servers: CallIceServer[];
  ice_transport_policy: 'all' | 'relay';
  closes_at: string | null;
}
