'use client';

import { useState } from 'react';
import { adminClient } from '@/lib/admin-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, formatInr, titleCase } from '@/lib/format';
import type { PaymentSummaryOut } from '@/lib/matter-client';
import { errorMessage, useAdminData } from '@/lib/use-admin-data';

function RefundForm({
  payment,
  onDone,
  onCancel,
}: {
  payment: PaymentSummaryOut;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { accessToken } = useAuth();
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remaining = (Number(payment.amount) - Number(payment.refunded_amount)).toFixed(2);

  async function submit() {
    if (!accessToken || busy || !reason.trim()) return;
    const label = amount.trim() ? formatInr(amount.trim()) : `the remaining ${formatInr(remaining)}`;
    if (!window.confirm(`Refund ${label} to the client? This cannot be undone.`)) return;
    setBusy(true);
    setError(null);
    try {
      await adminClient.refund(payment.payment_id, amount.trim() || undefined, reason.trim(), accessToken);
      onDone();
    } catch (err) {
      setError(errorMessage(err, 'The refund did not go through.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-2">
      <input
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        inputMode="decimal"
        placeholder={`Amount (blank = ${formatInr(remaining)})`}
        className="w-48 rounded-lg border border-slate-300 px-2 py-1 text-sm"
      />
      <input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (shown to the client)"
        maxLength={1000}
        className="min-w-0 flex-1 rounded-lg border border-slate-300 px-2 py-1 text-sm"
      />
      <button
        type="button"
        onClick={() => void submit()}
        disabled={busy || !reason.trim()}
        className="rounded-lg bg-rose-700 px-3 py-1 text-sm font-medium text-white hover:bg-rose-800 disabled:opacity-50"
      >
        Refund
      </button>
      <button type="button" onClick={onCancel} className="text-xs text-slate-500 hover:underline">
        Cancel
      </button>
      {error && <p className="w-full text-xs text-rose-600">{error}</p>}
    </div>
  );
}

export default function AdminPaymentsPage() {
  const { data, error, reload } = useAdminData(adminClient.payments);
  const [refunding, setRefunding] = useState<string | null>(null);

  return (
    <div>
      <p className="mb-3 text-xs text-slate-500">
        Cancelling a paid matter already refunds it in full. Use this for disputes and partial
        refunds, including after a matter has closed.
      </p>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {!data && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : data && data.items.length === 0 ? (
        <p className="text-sm text-slate-500">No payments yet.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data?.items.map((p) => {
            const refundable = Number(p.amount) - Number(p.refunded_amount) > 0;
            return (
              <li key={p.payment_id} className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-800">{p.matter_title}</span>
                  <span className="text-slate-700">{formatInr(p.amount)}</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {p.invoice_number} · {formatDateTime(p.created_at)} · {titleCase(p.status)}
                  {Number(p.refunded_amount) > 0 ? ` · ${formatInr(p.refunded_amount)} refunded` : ''}
                </p>
                {refundable && refunding !== p.payment_id && (
                  <button
                    type="button"
                    onClick={() => setRefunding(p.payment_id)}
                    className="mt-2 text-xs font-medium text-blue-700 hover:underline"
                  >
                    Refund…
                  </button>
                )}
                {refunding === p.payment_id && (
                  <RefundForm
                    payment={p}
                    onCancel={() => setRefunding(null)}
                    onDone={() => {
                      setRefunding(null);
                      reload();
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
