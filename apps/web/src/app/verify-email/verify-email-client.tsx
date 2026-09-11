'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { buttonClass } from '@/components/form';
import { ApiRequestError } from '@/lib/api-client';
import { authClient } from '@/lib/auth-client';

type Status = 'verifying' | 'success' | 'error' | 'missing-token';

export function VerifyEmailClient() {
  const token = useSearchParams().get('token');
  const [status, setStatus] = useState<Status>(token ? 'verifying' : 'missing-token');
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    authClient
      .verifyEmail(token)
      .then(() => {
        if (!cancelled) setStatus('success');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus('error');
        setMessage(err instanceof ApiRequestError ? err.message : 'Verification failed.');
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 px-6 py-16 text-center">
      {status === 'verifying' && <p className="text-slate-600">Verifying your email…</p>}

      {status === 'success' && (
        <>
          <h1 className="text-xl font-semibold text-emerald-700">Email verified</h1>
          <p className="text-sm text-slate-600">You&apos;re all set.</p>
          <Link href="/profile" className={`${buttonClass} mx-auto w-fit`}>
            Go to your profile
          </Link>
        </>
      )}

      {(status === 'error' || status === 'missing-token') && (
        <>
          <h1 className="text-xl font-semibold text-rose-700">Couldn&apos;t verify email</h1>
          <p className="text-sm text-slate-600">
            {message ?? 'This link is missing or invalid. Request a new one from your profile.'}
          </p>
          <Link href="/login" className="text-sm font-medium text-blue-700 hover:underline">
            Back to login
          </Link>
        </>
      )}
    </main>
  );
}
