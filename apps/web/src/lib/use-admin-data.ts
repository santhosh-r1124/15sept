'use client';

import { useCallback, useEffect, useState } from 'react';
import { ApiRequestError } from './api-client';
import { useAuth } from './auth-context';

/**
 * Loads data for an admin page with the current access token.
 *
 * `load` must be stable (wrap it in `useCallback` with its filters as dependencies): the data is
 * re-fetched whenever it changes, and after `reload()`.
 */
export function useAdminData<T>(load: (token: string) => Promise<T>) {
  const { accessToken } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    load(accessToken)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Could not load this page.'));
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, load, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, reload };
}

export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiRequestError ? err.message : fallback;
}
