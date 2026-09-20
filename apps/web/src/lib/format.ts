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
