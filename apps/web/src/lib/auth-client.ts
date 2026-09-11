import type { AuthUser, TokenPair } from '@legal-platform/auth';
import { apiFetch } from './api-client';

export interface RegisterPayload {
  email: string;
  password: string;
  display_name?: string;
  state_code?: string;
  preferred_language?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface UpdateProfilePayload {
  display_name?: string;
  state_code?: string;
  preferred_language?: string;
}

export interface MessageResponse {
  message: string;
}

/** Thin bindings for `/api/v1/auth/*` and `/api/v1/users/me`. See apps/api/app/api/v1/routes/auth.py. */
export const authClient = {
  register: (payload: RegisterPayload) =>
    apiFetch<TokenPair>('/api/v1/auth/register', { method: 'POST', body: payload }),

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

  updateProfile: (accessToken: string, payload: UpdateProfilePayload) =>
    apiFetch<AuthUser>('/api/v1/users/me', { method: 'PATCH', body: payload, token: accessToken }),

  verifyEmail: (token: string) =>
    apiFetch<MessageResponse>('/api/v1/auth/verify-email', { method: 'POST', body: { token } }),

  resendVerification: (email: string) =>
    apiFetch<MessageResponse>('/api/v1/auth/resend-verification', {
      method: 'POST',
      body: { email },
    }),

  forgotPassword: (email: string) =>
    apiFetch<MessageResponse>('/api/v1/auth/forgot-password', { method: 'POST', body: { email } }),

  resetPassword: (token: string, newPassword: string) =>
    apiFetch<MessageResponse>('/api/v1/auth/reset-password', {
      method: 'POST',
      body: { token, new_password: newPassword },
    }),
};
