'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, formatInr, STATUS_STYLES, titleCase } from '@/lib/format';
import { portalClient, type EarningsOut } from '@/lib/portal-client';

export default function EarningsPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const [data, setData] = useState<EarningsOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    portalClient
      .earnings(accessToken)
      .then((d) => !cancelled && setData(d))
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiRequestError ? err.message : 'Could not load earnings.');
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  if (authLoading) return <main className="mx-auto max-w-3xl px-6 py-8 text-sm">Loading…</main>;
  if (!user) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-teal-700 hover:underline">
          Log in
        </Link>{' '}
        to see your earnings.
      </main>
    );
  }

  const feePercent = data ? Number(data.summary.platform_fee_percent) : 0;
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Earnings</h1>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {data && (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'Earned (net)', value: data.summary.net_earned },
              { label: 'Earned (gross)', value: data.summary.gross_earned },
              { label: 'Platform fee', value: data.summary.platform_fee },
              { label: 'Pending', value: data.summary.pending },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-lg font-semibold text-slate-800">{formatInr(value)}</p>
                <p className="text-xs text-slate-500">{label}</p>
              </div>
            ))}
          </section>
          <p className="text-xs text-slate-400">
            Money counts as <b>earned</b> once you close a matter, and as <b>pending</b> while a paid
            matter is still in progress.{' '}
            {feePercent > 0
              ? `The platform fee (${data.summary.platform_fee_percent}%) applies to earned amounts.`
              : 'No platform fee is currently applied.'}
          </p>
          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Paid matters</h2>
            {data.items.length === 0 ? (
              <p className="text-sm text-slate-400">Nothing paid yet.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-slate-100">
                {data.items.map((i) => (
                  <li key={i.matter_id}>
                    <Link
                      href={`/matters/${i.matter_id}`}
                      className="flex items-baseline justify-between gap-3 py-2 text-sm hover:bg-slate-50"
                    >
                      <span className="text-slate-800">
                        {i.title}
                        <span className="text-xs text-slate-400">
                          {' '}
                          · paid {formatDateTime(i.paid_at)}
                        </span>
                      </span>
                      <span className="flex items-center gap-2 whitespace-nowrap">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLES[i.status] ?? ''}`}
                        >
                          {titleCase(i.status)}
                        </span>
                        {formatInr(i.amount)}
                        {Number(i.refunded) > 0 && (
                          <span className="text-xs text-amber-700">
                            (−{formatInr(i.refunded)} refunded)
                          </span>
                        )}
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
