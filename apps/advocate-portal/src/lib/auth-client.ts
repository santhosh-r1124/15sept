import type { AuthUser, TokenPair } from '@legal-platform/auth';
import type { AdvocateProfile } from '@legal-platform/shared';
import { apiFetch } from './api-client';

export interface AdvocateRegisterPayload {
  email: string;
  password: string;
  display_name: string;
  practice_areas?: string[];
  state_code: string;
  city: string;
  languages?: string[];
  consultation_fee?: string;
  bio?: string;
  experience_years?: number;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface AdvocateProfileUpdatePayload {
  practice_areas?: string[];
  state_code?: string;
  city?: string;
  languages?: string[];
  consultation_fee?: string;
  bio?: string;
  experience_years?: number;
}

export interface MessageResponse {
  message: string;
}

/** Bindings for `/api/v1/advocates/*`, `/api/v1/auth/*` and `/api/v1/users/me`. */
export const authClient = {
  registerAdvocate: (payload: AdvocateRegisterPayload) =>
    apiFetch<TokenPair>('/api/v1/advocates/register', { method: 'POST', body: payload }),

  login: (payload: LoginPayload) =>
    apiFetch<TokenPair>('/api/v1/auth/login', { method: 'POST', body: payload }),

  refresh: (refreshToken: string) =>
    apiFetch<TokenPair>('/api/v1/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }),

  logout: (refreshToken: string) =>
    apiFetch<MessageResponse>('/api/v1/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }),

  me: (accessToken: string) => apiFetch<AuthUser>('/api/v1/users/me', { token: accessToken }),

  advocateProfile: (accessToken: string) =>
    apiFetch<AdvocateProfile>('/api/v1/advocates/me', { token: accessToken }),

  updateAdvocateProfile: (accessToken: string, payload: AdvocateProfileUpdatePayload) =>
    apiFetch<AdvocateProfile>('/api/v1/advocates/me', {
      method: 'PATCH',
      body: payload,
      token: accessToken,
    }),

  resendVerification: (email: string) =>
    apiFetch<MessageResponse>('/api/v1/auth/resend-verification', {
      method: 'POST',
      body: { email },
    }),
};
