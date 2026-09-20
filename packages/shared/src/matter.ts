/** What a booked advocate engagement is for (FRD §9). Mirrored in `apps/api` (MatterServiceType). */
export const MATTER_SERVICE_TYPES = [
  'CONSULTATION',
  'DOCUMENT_DRAFT',
  'DOCUMENT_REVIEW',
  'DOCUMENT_MODIFICATION',
  'AFFIDAVIT_ASSISTANCE',
  'AGREEMENT_REVIEW',
] as const;
export type MatterServiceType = (typeof MATTER_SERVICE_TYPES)[number];

/** Consultation lengths on offer (FRD §9). */
export const CONSULTATION_MINUTES = [15, 30, 60] as const;
export type ConsultationMinutes = (typeof CONSULTATION_MINUTES)[number];

/** Matter lifecycle (roadmap Phase 8). Mirrored in `apps/api` (MatterStatus). */
export const MATTER_STATUSES = [
  'REQUESTED',
  'ACCEPTED',
  'PAID',
  'SCHEDULED',
  'CLOSED',
  'REJECTED',
  'CANCELLED',
] as const;
export type MatterStatus = (typeof MATTER_STATUSES)[number];

const TERMINAL: readonly MatterStatus[] = ['CLOSED', 'REJECTED', 'CANCELLED'];

/** A finished matter: no further actions, and its message thread is read-only. */
export function isTerminalMatterStatus(status: MatterStatus): boolean {
  return TERMINAL.includes(status);
}
