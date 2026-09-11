import type { VerificationStatus } from './roles';

/**
 * Advocate-specific profile fields. Mirrors `app/schemas/advocate.py::AdvocateProfileOut`
 * (field names, snake_case, must match the wire format exactly).
 */
export interface AdvocateProfile {
  id: string;
  user_id: string;
  practice_areas: string[];
  /** ISO-3166-2:IN state code. */
  state_code: string;
  city: string;
  languages: string[];
  /** Decimal, serialised as a string by Pydantic (e.g. "1500.00"). */
  consultation_fee: string | null;
  bio: string | null;
  experience_years: number | null;
  verification_status: VerificationStatus;
  verification_note: string | null;
  availability: Record<string, unknown> | null;
}
