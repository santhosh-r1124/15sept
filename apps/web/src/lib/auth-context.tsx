'use client';

import type { AuthUser } from '@legal-platform/auth';
import { isTokenExpired } from '@legal-platform/auth';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ApiRequestError } from './api-client';
import {
  authClient,
  type LoginPayload,
  type RegisterPayload,
  type UpdateProfilePayload,
} from './auth-client';

const ACCESS_TOKEN_KEY = 'lp_access_token';
const REFRESH_TOKEN_KEY = 'lp_refresh_token';

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  /** True while the initial session restore (from localStorage) is in flight. */
  loading: boolean;
  register: (payload: RegisterPayload) => Promise<void>;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (payload: UpdateProfilePayload) => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredTokens(): { access: string | null; refresh: string | null } {
  if (typeof window === 'undefined') return { access: null, refresh: null };
  try {
    return {
      access: window.localStorage.getItem(ACCESS_TOKEN_KEY),
      refresh: window.localStorage.getItem(REFRESH_TOKEN_KEY),
    };
  } catch {
    return { access: null, refresh: null };
  }
}

function storeTokens(access: string | null, refresh: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (access) window.localStorage.setItem(ACCESS_TOKEN_KEY, access);
    else window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    if (refresh) window.localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
    else window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // Private browsing / storage disabled — the session just won't survive a reload.
  }
}

/**
 * Client-side auth session. Tokens live in `localStorage` (Phase 13 hardening
 * may move refresh tokens to an httpOnly cookie); the access token is held in
 * memory + storage and attached per-request via `apiFetch({ token })`.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const applyTokens = useCallback((access: string, refresh: string) => {
    setAccessToken(access);
    setRefreshToken(refresh);
    storeTokens(access, refresh);
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    setRefreshToken(null);
    storeTokens(null, null);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function restore(): Promise<void> {
      const { access, refresh } = readStoredTokens();
      if (!access || !refresh) {
        setLoading(false);
        return;
      }
      try {
        let currentAccess = access;
        if (isTokenExpired(currentAccess)) {
          const pair = await authClient.refresh(refresh);
          if (cancelled) return;
          currentAccess = pair.access_token;
          applyTokens(pair.access_token, pair.refresh_token);
        } else {
          setAccessToken(currentAccess);
          setRefreshToken(refresh);
        }
        const me = await authClient.me(currentAccess);
        if (!cancelled) setUser(me);
      } catch {
        if (!cancelled) clearSession();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void restore();
    return () => {
      cancelled = true;
    };
    // Deliberately runs once on mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const register = useCallback(
    async (payload: RegisterPayload) => {
      const pair = await authClient.register(payload);
      applyTokens(pair.access_token, pair.refresh_token);
      setUser(await authClient.me(pair.access_token));
    },
    [applyTokens],
  );

  const login = useCallback(
    async (payload: LoginPayload) => {
      const pair = await authClient.login(payload);
      applyTokens(pair.access_token, pair.refresh_token);
      setUser(await authClient.me(pair.access_token));
    },
    [applyTokens],
  );

  const logout = useCallback(async () => {
    if (refreshToken) {
      try {
        await authClient.logout(refreshToken);
      } catch {
        // Best-effort — clear the local session regardless of API reachability.
      }
    }
    clearSession();
  }, [refreshToken, clearSession]);

  const updateProfile = useCallback(
    async (payload: UpdateProfilePayload) => {
      if (!accessToken) throw new ApiRequestError(401, 'unauthorized', 'Not signed in.');
      setUser(await authClient.updateProfile(accessToken, payload));
    },
    [accessToken],
  );

  const refreshUser = useCallback(async () => {
    if (!accessToken) return;
    setUser(await authClient.me(accessToken));
  }, [accessToken]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, accessToken, loading, register, login, logout, updateProfile, refreshUser }),
    [user, accessToken, loading, register, login, logout, updateProfile, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
