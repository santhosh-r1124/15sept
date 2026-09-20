'use client';

import type { MatterStatus } from '@legal-platform/shared';
import { useEffect, useState } from 'react';
import { formatDateTime, formatInr } from '@/lib/format';
import { portalClient, type MatterPaymentOut } from '@/lib/portal-client';

// Statuses in which a payment can exist. (A matter cancelled before payment has none.)
const PAYABLE: MatterStatus[] = ['PAID', 'SCHEDULED', 'CLOSED', 'CANCELLED'];

/** The client's payment for this matter, any refunds, and the invoice. */
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

  useEffect(() => {
    if (!PAYABLE.includes(status)) return;
    let cancelled = false;
    portalClient
      .payment(matterId, token)
      .then((p) => !cancelled && setInfo(p))
      .catch(() => {
        // 404 means "never paid"; anything else is transient - either way the card stays hidden.
      });
    return () => {
      cancelled = true;
    };
  }, [matterId, token, status]);

  if (!info) return null;
  const { payment, invoice } = info;
  const refunded = Number(payment.refunded_amount) > 0;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Payment</h2>
      <p className="text-slate-700">
        Client paid {formatInr(payment.amount)} on {formatDateTime(payment.created_at)}
      </p>
      {refunded && (
        <p className="mt-1 text-amber-700">
          {payment.status === 'REFUNDED' ? 'Refunded in full' : 'Partly refunded'}:{' '}
          {formatInr(payment.refunded_amount)} — this reduces what you earn from this matter.
        </p>
      )}
      <button
        type="button"
        onClick={() => void portalClient.openInvoice(invoice.id, token)}
        className="mt-3 text-xs font-medium text-teal-700 hover:underline"
      >
        View invoice {invoice.invoice_number}
      </button>
    </section>
  );
}
