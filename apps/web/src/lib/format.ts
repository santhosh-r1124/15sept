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
