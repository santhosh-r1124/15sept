'use client';

import type { MatterStatus } from '@legal-platform/shared';
import { useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { formatDateTime, formatInr } from '@/lib/format';
import { matterClient, type MatterPaymentOut } from '@/lib/matter-client';

// Statuses in which a payment can exist. (A matter cancelled before payment has none.)
const PAYABLE: MatterStatus[] = ['PAID', 'SCHEDULED', 'CLOSED', 'CANCELLED'];

/** What was paid, whether any of it came back, and the invoice. */
export function PaymentCard({
  matterId,
  token,
  status,
}: {
  matterId: string;
  token: string;
  status: MatterStatus;
}) {
  const [info, setInfo] = useState<MatterPaymentOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!PAYABLE.includes(status)) return;
    let cancelled = false;
    matterClient
      .payment(matterId, token)
      .then((p) => !cancelled && setInfo(p))
      .catch((err) => {
        // 404 just means "never paid" (cancelled first) - nothing to show.
        if (!cancelled && !(err instanceof ApiRequestError && err.status === 404))
          setError('Could not load payment details.');
      });
    return () => {
      cancelled = true;
    };
  }, [matterId, token, status]);

  if (!info) return error ? <p className="mt-4 text-xs text-rose-600">{error}</p> : null;

  const { payment, invoice } = info;
  const refunded = Number(payment.refunded_amount) > 0;
  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Payment</h2>
      <p className="text-slate-700">
        Paid {formatInr(payment.amount)} on {formatDateTime(payment.created_at)}
      </p>
      {refunded && (
        <p className="mt-1 text-emerald-700">
          {payment.status === 'REFUNDED' ? 'Refunded in full' : 'Partly refunded'}:{' '}
          {formatInr(payment.refunded_amount)}
        </p>
      )}
      {payment.refunds.length > 0 && (
        <ul className="mt-1 text-xs text-slate-500">
          {payment.refunds.map((r) => (
            <li key={r.id}>
              {formatInr(r.amount)} — {r.reason}
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={() => void matterClient.openInvoice(invoice.id, token)}
        className="mt-3 text-xs font-medium text-blue-700 hover:underline"
      >
        View invoice {invoice.invoice_number}
      </button>
    </section>
  );
}
