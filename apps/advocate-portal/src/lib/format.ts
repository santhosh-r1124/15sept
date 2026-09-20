// Words that stay upper-case rather than being title-cased ("IT_LAW" -> "IT Law").
const ACRONYMS = new Set(['IT', 'IP', 'NDA']);

/** "DOCUMENT_REVIEW" -> "Document Review", "IT_LAW" -> "IT Law". */
export function titleCase(enumKey: string): string {
  return enumKey
    .split('_')
    .map((w) => (ACRONYMS.has(w) || w.length === 0 ? w : w[0] + w.slice(1).toLowerCase()))
    .join(' ');
}

/** "600.00" -> "₹600.00". Amounts stay strings end to end so decimals never pass through floats. */
export function formatInr(amount: string | null): string {
  return amount ? `₹${amount}` : '—';
}

const HAS_OFFSET = /(Z|[+-]\d{2}:?\d{2})$/i;

/**
 * The API sends some timestamps (`created_at`, `updated_at`) as UTC *without* an offset
 * ("2026-09-20T08:05:12"). `new Date()` reads an offset-less string as *local* time, which shows
 * an Indian user every such time 5½ hours early - so treat it as UTC explicitly.
 */
export function parseApiDate(iso: string): Date {
  return new Date(HAS_OFFSET.test(iso) ? iso : `${iso}Z`);
}

export function formatDateTime(iso: string | null): string {
  return iso ? parseApiDate(iso).toLocaleString() : '—';
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Badge colours per matter status, shared by the list and detail pages. */
export const STATUS_STYLES: Record<string, string> = {
  REQUESTED: 'bg-amber-100 text-amber-800',
  ACCEPTED: 'bg-blue-100 text-blue-800',
  PAID: 'bg-teal-100 text-teal-800',
  SCHEDULED: 'bg-teal-100 text-teal-800',
  CLOSED: 'bg-emerald-100 text-emerald-800',
  REJECTED: 'bg-rose-100 text-rose-800',
  CANCELLED: 'bg-slate-200 text-slate-700',
};
