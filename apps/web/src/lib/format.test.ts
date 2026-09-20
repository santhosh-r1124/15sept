import { describe, expect, it } from 'vitest';
import { formatDateTime, parseApiDate } from './format';

describe('parseApiDate', () => {
  it('reads an offset-less API timestamp as UTC, not local time', () => {
    // created_at / updated_at come back like this; new Date() alone would use the local zone.
    expect(parseApiDate('2026-09-20T08:05:12.797993').toISOString()).toBe('2026-09-20T08:05:12.797Z');
  });

  it('leaves timestamps that already carry an offset alone', () => {
    expect(parseApiDate('2026-09-20T08:05:16.950633Z').toISOString()).toBe('2026-09-20T08:05:16.950Z');
    expect(parseApiDate('2026-09-20T13:35:16+05:30').toISOString()).toBe('2026-09-20T08:05:16.000Z');
    expect(parseApiDate('2026-09-20T02:35:16-05:30').toISOString()).toBe('2026-09-20T08:05:16.000Z');
  });

  it('gives the same instant whether or not the offset is spelled out', () => {
    expect(parseApiDate('2026-09-20T08:05:12').getTime()).toBe(
      parseApiDate('2026-09-20T08:05:12Z').getTime(),
    );
  });
});

describe('formatDateTime', () => {
  it('shows a dash for null', () => {
    expect(formatDateTime(null)).toBe('—');
  });
});
