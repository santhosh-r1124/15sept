import { describe, expect, it } from 'vitest';
import { CONSULTATION_MINUTES, MATTER_STATUSES, isTerminalMatterStatus } from './matter';

describe('matter', () => {
  it('treats closed, rejected and cancelled as terminal', () => {
    const terminal = MATTER_STATUSES.filter(isTerminalMatterStatus);
    expect(terminal).toEqual(['CLOSED', 'REJECTED', 'CANCELLED']);
  });

  it('offers the FRD consultation lengths', () => {
    expect([...CONSULTATION_MINUTES]).toEqual([15, 30, 60]);
  });
});
