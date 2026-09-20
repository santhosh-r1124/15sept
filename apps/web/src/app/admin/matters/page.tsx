'use client';

import { useCallback, useState } from 'react';
import { adminClient } from '@/lib/admin-client';
import { formatDateTime, formatInr, titleCase } from '@/lib/format';
import { useAdminData } from '@/lib/use-admin-data';

const STATUSES = [
  'REQUESTED',
  'ACCEPTED',
  'PAID',
  'SCHEDULED',
  'CLOSED',
  'REJECTED',
  'CANCELLED',
];

export default function AdminMattersPage() {
  const [status, setStatus] = useState('');
  const load = useCallback(
    (token: string) => adminClient.matters(token, { status: status || undefined }),
    [status],
  );
  const { data, error } = useAdminData(load);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="">Any status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {titleCase(s)}
            </option>
          ))}
        </select>
        {data && <span className="text-xs text-slate-500">{data.total} total</span>}
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Read-only oversight. Matters are run by the client and advocate; refunds are on the Payments
        tab.
      </p>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {!data && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Matter</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Client</th>
                <th className="px-3 py-2 font-medium">Advocate</th>
                <th className="px-3 py-2 font-medium">Fee</th>
                <th className="px-3 py-2 font-medium">Opened</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((m) => (
                <tr key={m.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-3 py-2">
                    <div className="font-medium text-slate-800">{m.title}</div>
                    <div className="text-xs text-slate-500">{titleCase(m.service_type)}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{titleCase(m.status)}</td>
                  <td className="px-3 py-2 text-slate-600">{m.consumer_name ?? '—'}</td>
                  <td className="px-3 py-2 text-slate-600">{m.advocate_name ?? '—'}</td>
                  <td className="px-3 py-2 text-slate-600">{formatInr(m.quoted_fee)}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">{formatDateTime(m.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && data.items.length === 0 && (
            <p className="p-4 text-sm text-slate-500">No matters.</p>
          )}
        </div>
      )}
    </div>
  );
}
