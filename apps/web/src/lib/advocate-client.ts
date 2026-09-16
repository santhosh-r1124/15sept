import { apiFetch } from './api-client';

export interface AdvocateDirectoryEntry {
  id: string;
  display_name: string | null;
  practice_areas: string[];
  state_code: string;
  city: string;
  languages: string[];
  /** Decimal, serialised as a string by Pydantic (e.g. "1500.00"). */
  consultation_fee: string | null;
  bio: string | null;
  experience_years: number | null;
  availability: Record<string, unknown> | null;
}

export interface PaginatedAdvocateDirectory {
  items: AdvocateDirectoryEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdvocateSearchFilters {
  practice_area?: string;
  state_code?: string;
  city?: string;
  language?: string;
  min_experience_years?: number;
  max_consultation_fee?: string;
  limit?: number;
  offset?: number;
}

function toQueryString(filters: AdvocateSearchFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

/** Bindings for `/api/v1/advocates/*` (public, Phase 7 discovery slice). */
export const advocateClient = {
  search: (filters: AdvocateSearchFilters = {}) =>
    apiFetch<PaginatedAdvocateDirectory>(`/api/v1/advocates${toQueryString(filters)}`),

  get: (advocateId: string) =>
    apiFetch<AdvocateDirectoryEntry>(`/api/v1/advocates/${advocateId}`),
};
