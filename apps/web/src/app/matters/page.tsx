'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatInr, titleCase } from '@/lib/format';
import { matterClient, type MatterOut } from '@/lib/matter-client';

export default function MattersPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const [matters, setMatters] = useState<MatterOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    matterClient
      .list(accessToken)
      .then((res) => {
        if (!cancelled) setMatters(res.items);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiRequestError ? err.message : 'Could not load your matters.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  if (authLoading) return <main className="mx-auto max-w-2xl px-4 py-6 text-sm">Loading…</main>;
  if (!user) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-6 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-blue-700 hover:underline">
          Log in
        </Link>{' '}
        to see your matters.
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">My matters</h1>
      <p className="mb-4 text-xs text-slate-500">
        Advocate requests you have made, and where each one stands.
      </p>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {matters === null && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : matters && matters.length === 0 ? (
        <p className="text-sm text-slate-500">
          Nothing yet.{' '}
          <Link href="/advocates" className="font-medium text-blue-700 hover:underline">
            Find an advocate
          </Link>{' '}
          to get started.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {matters?.map((m) => (
            <li key={m.id}>
              <Link
                href={`/matters/${m.id}`}
                className="block rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-500"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-800">{m.title}</span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {titleCase(m.status)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {titleCase(m.service_type)}
                  {m.consultation_minutes ? ` · ${m.consultation_minutes} min` : ''} ·{' '}
                  {m.advocate.display_name ?? 'Advocate'} · {formatInr(m.quoted_fee)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
