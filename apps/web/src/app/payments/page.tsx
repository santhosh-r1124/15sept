'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, formatInr, titleCase } from '@/lib/format';
import { matterClient, type PaymentSummaryOut } from '@/lib/matter-client';

export default function PaymentsPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const [items, setItems] = useState<PaymentSummaryOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    matterClient
      .listPayments(accessToken)
      .then((res) => !cancelled && setItems(res.items))
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiRequestError ? err.message : 'Could not load payments.');
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
        to see your payments.
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Payments</h1>
      <p className="mb-4 text-xs text-slate-500">What you have paid, refunds, and your invoices.</p>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {items === null && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : items && items.length === 0 ? (
        <p className="text-sm text-slate-500">No payments yet.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items?.map((p) => (
            <li key={p.payment_id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-baseline justify-between gap-2">
                <Link
                  href={`/matters/${p.matter_id}`}
                  className="font-medium text-slate-800 hover:underline"
                >
                  {p.matter_title}
                </Link>
                <span className="text-sm text-slate-700">{formatInr(p.amount)}</span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {formatDateTime(p.created_at)} · {titleCase(p.status)}
                {Number(p.refunded_amount) > 0 ? ` · ${formatInr(p.refunded_amount)} refunded` : ''}
              </p>
              <button
                type="button"
                onClick={() => accessToken && void matterClient.openInvoice(p.invoice_id, accessToken)}
                className="mt-2 text-xs font-medium text-blue-700 hover:underline"
              >
                View invoice {p.invoice_number}
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
