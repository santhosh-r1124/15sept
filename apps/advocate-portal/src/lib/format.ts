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

export function formatDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—';
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
