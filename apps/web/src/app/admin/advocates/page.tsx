'use client';

import { useCallback, useState } from 'react';
import { adminClient, type AdminAdvocate } from '@/lib/admin-client';
import { useAuth } from '@/lib/auth-context';
import { formatInr, titleCase } from '@/lib/format';
import { errorMessage, useAdminData } from '@/lib/use-admin-data';

const STATUS_STYLE: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-800',
  IN_REVIEW: 'bg-sky-100 text-sky-800',
  VERIFIED: 'bg-emerald-100 text-emerald-800',
  REJECTED: 'bg-rose-100 text-rose-800',
};

function AdvocateCard({ a, onChanged }: { a: AdminAdvocate; onChanged: () => void }) {
  const { accessToken } = useAuth();
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(kind: 'verify' | 'reject') {
    if (!accessToken || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === 'verify') await adminClient.verifyAdvocate(a.id, note.trim() || undefined, accessToken);
      else await adminClient.rejectAdvocate(a.id, note.trim(), accessToken);
      setNote('');
      onChanged();
    } catch (err) {
      setError(errorMessage(err, 'That did not work.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <span className="font-medium text-slate-900">{a.display_name ?? 'Unnamed advocate'}</span>
          <span className="ml-2 text-xs text-slate-500">{a.email}</span>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[a.verification_status] ?? ''}`}
        >
          {titleCase(a.verification_status)}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        {a.city}, {a.state_code} · {a.experience_years ?? '?'} yrs · {formatInr(a.consultation_fee)}/hr ·{' '}
        {a.languages.join(', ') || 'no languages listed'}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {a.practice_areas.map((p) => titleCase(p)).join(', ') || 'No practice areas'}
      </p>
      {a.bio && <p className="mt-2 text-slate-700">{a.bio}</p>}
      {a.verification_note && (
        <p className="mt-2 text-xs text-slate-500">Last note: {a.verification_note}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Note (required to reject)"
          maxLength={1000}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        {a.verification_status !== 'VERIFIED' && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void act('verify')}
            className="rounded-lg bg-emerald-700 px-3 py-1.5 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
          >
            Verify
          </button>
        )}
        {a.verification_status !== 'REJECTED' && (
          <button
            type="button"
            disabled={busy || !note.trim()}
            onClick={() => void act('reject')}
            className="rounded-lg border border-rose-300 px-3 py-1.5 text-rose-700 hover:bg-rose-50 disabled:opacity-50"
          >
            Reject
          </button>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
    </li>
  );
}

export default function AdvocatesPage() {
  const [status, setStatus] = useState('PENDING');
  const load = useCallback(
    (token: string) => adminClient.advocates(token, { status: status || undefined }),
    [status],
  );
  const { data, error, reload } = useAdminData(load);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="PENDING">Pending</option>
          <option value="IN_REVIEW">In review</option>
          <option value="VERIFIED">Verified</option>
          <option value="REJECTED">Rejected</option>
          <option value="">All</option>
        </select>
        {data && <span className="text-xs text-slate-500">{data.total} total</span>}
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Only verified advocates appear in the public directory and can be booked. Check the bar
        council details before verifying; the advocate is notified either way.
      </p>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {!data && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : data && data.items.length === 0 ? (
        <p className="text-sm text-slate-500">No advocates in this state.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data?.items.map((a) => (
            <AdvocateCard key={`${a.id}-${a.verification_status}`} a={a} onChanged={reload} />
          ))}
        </ul>
      )}
    </div>
  );
}
