'use client';

import type { AuthUser } from '@legal-platform/auth';
import { isTokenExpired } from '@legal-platform/auth';
import type { AdvocateProfile } from '@legal-platform/shared';
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
  type AdvocateProfileUpdatePayload,
  type AdvocateRegisterPayload,
  type LoginPayload,
} from './auth-client';

const ACCESS_TOKEN_KEY = 'lp_advocate_access_token';
const REFRESH_TOKEN_KEY = 'lp_advocate_refresh_token';

interface AuthContextValue {
  user: AuthUser | null;
  profile: AdvocateProfile | null;
  accessToken: string | null;
  loading: boolean;
  registerAdvocate: (payload: AdvocateRegisterPayload) => Promise<void>;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (payload: AdvocateProfileUpdatePayload) => Promise<void>;
  refresh: () => Promise<void>;
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<AdvocateProfile | null>(null);
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
    setProfile(null);
    setAccessToken(null);
    setRefreshToken(null);
    storeTokens(null, null);
  }, []);

  const loadSession = useCallback(async (access: string) => {
    const [me, advocateProfile] = await Promise.all([
      authClient.me(access),
      authClient.advocateProfile(access),
    ]);
    setUser(me);
    setProfile(advocateProfile);
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
        if (!cancelled) await loadSession(currentAccess);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const registerAdvocate = useCallback(
    async (payload: AdvocateRegisterPayload) => {
      const pair = await authClient.registerAdvocate(payload);
      applyTokens(pair.access_token, pair.refresh_token);
      await loadSession(pair.access_token);
    },
    [applyTokens, loadSession],
  );

  const login = useCallback(
    async (payload: LoginPayload) => {
      const pair = await authClient.login(payload);
      applyTokens(pair.access_token, pair.refresh_token);
      await loadSession(pair.access_token);
    },
    [applyTokens, loadSession],
  );

  const logout = useCallback(async () => {
    if (refreshToken) {
      try {
        await authClient.logout(refreshToken);
      } catch {
        // Best-effort — clear the local session regardless.
      }
    }
    clearSession();
  }, [refreshToken, clearSession]);

  const updateProfile = useCallback(
    async (payload: AdvocateProfileUpdatePayload) => {
      if (!accessToken) throw new ApiRequestError(401, 'unauthorized', 'Not signed in.');
      setProfile(await authClient.updateAdvocateProfile(accessToken, payload));
    },
    [accessToken],
  );

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    await loadSession(accessToken);
  }, [accessToken, loadSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      profile,
      accessToken,
      loading,
      registerAdvocate,
      login,
      logout,
      updateProfile,
      refresh,
    }),
    [user, profile, accessToken, loading, registerAdvocate, login, logout, updateProfile, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
