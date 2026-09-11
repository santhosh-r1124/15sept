/** Platform roles for RBAC (roadmap Phase 1). Mirrored in `apps/api`. */
export const ROLES = [
  'CONSUMER',
  'ADVOCATE',
  'ADMIN',
  'LEGAL_ADMIN',
  'ENTERPRISE_USER',
] as const;

export type Role = (typeof ROLES)[number];

/** Advocate verification lifecycle. */
export const VERIFICATION_STATUSES = ['PENDING', 'IN_REVIEW', 'VERIFIED', 'REJECTED'] as const;
export type VerificationStatus = (typeof VERIFICATION_STATUSES)[number];

export function isRole(value: string): value is Role {
  return (ROLES as readonly string[]).includes(value);
}

/** Coarse capability check used by both frontends before calling the API. */
export function hasAdminAccess(role: Role): boolean {
  return role === 'ADMIN' || role === 'LEGAL_ADMIN';
}
