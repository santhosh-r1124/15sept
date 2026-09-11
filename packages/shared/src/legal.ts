/** Legal query categories (FRD §6). Mirrored in `apps/api` as an enum. */
export const LEGAL_CATEGORIES = [
  'CONSUMER_LAW',
  'CONTRACT_LAW',
  'IT_LAW',
  'CYBER_LAW',
  'DATA_PROTECTION',
  'IP_LAW',
  'PROPERTY_LAW',
  'EMPLOYMENT_LAW',
  'CORPORATE_LAW',
  'FAMILY_LAW',
  'CRIMINAL_LAW',
  'TAX_LAW',
  'DOCUMENT_GUIDANCE',
  'ADVOCATE_REQUIRED',
  'OUT_OF_SCOPE',
] as const;

export type LegalCategory = (typeof LEGAL_CATEGORIES)[number];

/** Internal risk classification for a query (FRD §13). */
export const RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

/** Which body of law a question potentially depends on (FRD §12). */
export const JURISDICTION_SCOPES = [
  'CENTRAL',
  'STATE',
  'LOCAL',
  'DISTRICT',
  'COURT',
  'REGISTRATION_AUTHORITY',
  'STAMP_DUTY',
  'UNKNOWN',
] as const;
export type JurisdictionScope = (typeof JURISDICTION_SCOPES)[number];

/**
 * Indian states and union territories (ISO 3166-2:IN short codes).
 * Used for advocate location, jurisdiction detection and stamp-duty routing.
 */
export const INDIAN_STATES = [
  'AN', 'AP', 'AR', 'AS', 'BR', 'CH', 'CT', 'DN', 'DL', 'GA', 'GJ', 'HR', 'HP',
  'JK', 'JH', 'KA', 'KL', 'LA', 'LD', 'MP', 'MH', 'MN', 'ML', 'MZ', 'NL', 'OR',
  'PY', 'PB', 'RJ', 'SK', 'TN', 'TG', 'TR', 'UP', 'UT', 'WB',
] as const;
export type IndianStateCode = (typeof INDIAN_STATES)[number];

/** Document types the Legal Document Assistant supports (FRD §7). */
export const DOCUMENT_TYPES = [
  'RENTAL_AGREEMENT',
  'EMPLOYMENT_AGREEMENT',
  'NDA',
  'AFFIDAVIT',
  'DECLARATION',
  'BUSINESS_AGREEMENT',
  'PARTNERSHIP_DOCUMENT',
  'AUTHORIZATION_LETTER',
  'SERVICE_AGREEMENT',
  'LEGAL_NOTICE',
  'OTHER',
] as const;
export type DocumentType = (typeof DOCUMENT_TYPES)[number];

export function isLegalCategory(value: string): value is LegalCategory {
  return (LEGAL_CATEGORIES as readonly string[]).includes(value);
}

export function isRiskLevel(value: string): value is RiskLevel {
  return (RISK_LEVELS as readonly string[]).includes(value);
}

/** Risk levels that must surface an "consult an advocate" recommendation. */
export function requiresAdvocate(risk: RiskLevel): boolean {
  return risk === 'HIGH' || risk === 'CRITICAL';
}
