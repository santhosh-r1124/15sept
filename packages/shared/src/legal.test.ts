import { describe, expect, it } from 'vitest';
import { isLegalCategory, isRiskLevel, requiresAdvocate } from './legal';
import { hasAdminAccess, isRole } from './roles';

describe('legal guards', () => {
  it('recognises valid legal categories', () => {
    expect(isLegalCategory('IT_LAW')).toBe(true);
    expect(isLegalCategory('SPACE_LAW')).toBe(false);
  });

  it('recognises valid risk levels', () => {
    expect(isRiskLevel('CRITICAL')).toBe(true);
    expect(isRiskLevel('SEVERE')).toBe(false);
  });

  it('flags advocate need for HIGH and CRITICAL only', () => {
    expect(requiresAdvocate('LOW')).toBe(false);
    expect(requiresAdvocate('MEDIUM')).toBe(false);
    expect(requiresAdvocate('HIGH')).toBe(true);
    expect(requiresAdvocate('CRITICAL')).toBe(true);
  });
});

describe('role guards', () => {
  it('recognises platform roles', () => {
    expect(isRole('ADVOCATE')).toBe(true);
    expect(isRole('SUPERUSER')).toBe(false);
  });

  it('grants admin access to ADMIN and LEGAL_ADMIN', () => {
    expect(hasAdminAccess('ADMIN')).toBe(true);
    expect(hasAdminAccess('LEGAL_ADMIN')).toBe(true);
    expect(hasAdminAccess('CONSUMER')).toBe(false);
  });
});
