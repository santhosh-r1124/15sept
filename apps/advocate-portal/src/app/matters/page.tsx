'use client';

import { MATTER_STATUSES, type MatterStatus } from '@legal-platform/shared';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatInr, STATUS_STYLES, titleCase } from '@/lib/format';
import { portalClient, type MatterOut } from '@/lib/portal-client';

function MattersList() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const params = useSearchParams();
  const raw = params.get('status');
  const status = MATTER_STATUSES.find((s) => s === raw) as MatterStatus | undefined;
  const [matters, setMatters] = useState<MatterOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setMatters(null);
    portalClient
      .listMatters(accessToken, status)
      .then((res) => !cancelled && setMatters(res.items))
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiRequestError ? err.message : 'Could not load matters.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, status]);

  if (authLoading) return <main className="mx-auto max-w-3xl px-6 py-8 text-sm">Loading…</main>;
  if (!user) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-teal-700 hover:underline">
          Log in
        </Link>{' '}
        to see your matters.
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Matters</h1>
      <nav className="flex flex-wrap gap-2 text-xs">
        <Link
          href="/matters"
          className={`rounded-full border px-3 py-1 ${!status ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-slate-300 text-slate-600'}`}
        >
          All
        </Link>
        {MATTER_STATUSES.map((s) => (
          <Link
            key={s}
            href={`/matters?status=${s}`}
            className={`rounded-full border px-3 py-1 ${status === s ? 'border-teal-700 bg-teal-50 text-teal-800' : 'border-slate-300 text-slate-600'}`}
          >
            {titleCase(s)}
          </Link>
        ))}
      </nav>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {matters === null && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : matters && matters.length === 0 ? (
        <p className="text-sm text-slate-500">No matters here.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {matters?.map((m) => (
            <li key={m.id}>
              <Link
                href={`/matters/${m.id}`}
                className="block rounded-xl border border-slate-200 bg-white p-4 hover:border-teal-500"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-800">{m.title}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLES[m.status] ?? ''}`}
                  >
                    {titleCase(m.status)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {titleCase(m.service_type)}
                  {m.consultation_minutes ? ` · ${m.consultation_minutes} min` : ''} ·{' '}
                  {m.consumer.display_name ?? 'Client'}
                  {m.consumer.verified ? ' (verified)' : ''} · {formatInr(m.quoted_fee)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

export default function MattersPage() {
  // useSearchParams needs a Suspense boundary for static rendering.
  return (
    <Suspense fallback={<main className="mx-auto max-w-3xl px-6 py-8 text-sm">Loading…</main>}>
      <MattersList />
    </Suspense>
  );
}
