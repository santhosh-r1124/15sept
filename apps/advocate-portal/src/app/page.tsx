'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, formatInr } from '@/lib/format';
import { portalClient, type AdvocateDashboard } from '@/lib/portal-client';

function Stat({
  label,
  value,
  href,
  hint,
}: {
  label: string;
  value: number;
  href?: string;
  hint?: string;
}) {
  const body = (
    <div
      className={`rounded-xl border bg-white p-4 ${
        value > 0 && href ? 'border-teal-300' : 'border-slate-200'
      }`}
    >
      <p className="text-2xl font-semibold text-slate-800">{value}</p>
      <p className="text-sm text-slate-600">{label}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
  return href ? (
    <Link href={href} className="hover:opacity-90">
      {body}
    </Link>
  ) : (
    body
  );
}

export default function DashboardPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const [data, setData] = useState<AdvocateDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    portalClient
      .dashboard(accessToken)
      .then((d) => !cancelled && setData(d))
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiRequestError ? err.message : 'Could not load the dashboard.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  if (authLoading) return <main className="mx-auto max-w-3xl px-6 py-10 text-sm">Loading…</main>;

  if (!user) {
    return (
      <main className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Advocate Portal</h1>
        <p className="text-slate-600">
          Accept requests, run consultations, exchange documents and track your earnings.
        </p>
        <div className="flex gap-2">
          <Link
            href="/login"
            className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
          >
            Log in
          </Link>
          <Link
            href="/register"
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            Register as an advocate
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">
          Welcome{user.display_name ? `, ${user.display_name}` : ''}
        </h1>
        <p className="text-xs text-slate-500">What needs your attention today.</p>
      </div>
      {error && (
        <p className="text-sm text-rose-600">
          {error}{' '}
          {error.toLowerCase().includes('permission') && '(This portal is for advocate accounts.)'}
        </p>
      )}

      {data && (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Stat label="New requests" value={data.new_requests} href="/matters?status=REQUESTED" />
            <Stat
              label="To schedule"
              value={data.to_schedule}
              href="/matters?status=PAID"
              hint="Paid consultations"
            />
            <Stat
              label="Awaiting payment"
              value={data.awaiting_payment}
              href="/matters?status=ACCEPTED"
            />
            <Stat label="Client replies waiting" value={data.awaiting_reply} href="/matters" />
            <Stat
              label="Documents requested"
              value={data.open_document_requests}
              href="/matters"
              hint="Not yet received"
            />
            <Link href="/earnings" className="hover:opacity-90">
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-2xl font-semibold text-slate-800">
                  {formatInr(data.earnings.net_earned)}
                </p>
                <p className="text-sm text-slate-600">Earned</p>
                <p className="mt-1 text-xs text-slate-400">
                  {formatInr(data.earnings.pending)} pending
                </p>
              </div>
            </Link>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Upcoming appointments</h2>
            {data.upcoming_appointments.length === 0 ? (
              <p className="text-sm text-slate-400">Nothing scheduled.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-slate-100">
                {data.upcoming_appointments.map((a) => (
                  <li key={a.matter_id}>
                    <Link
                      href={`/matters/${a.matter_id}`}
                      className="flex items-baseline justify-between gap-3 py-2 text-sm hover:bg-slate-50"
                    >
                      <span className="text-slate-800">
                        {a.title}
                        <span className="text-slate-400"> · {a.client_name ?? 'Client'}</span>
                      </span>
                      <span className="whitespace-nowrap text-xs text-slate-500">
                        {formatDateTime(a.scheduled_at)}
                        {a.consultation_minutes ? ` · ${a.consultation_minutes} min` : ''}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
