'use client';

import { useCallback, useState } from 'react';
import { adminClient, type QueryReview } from '@/lib/admin-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, titleCase } from '@/lib/format';
import { errorMessage, useAdminData } from '@/lib/use-admin-data';

const selectCls = 'rounded-lg border border-slate-300 px-2 py-1.5 text-sm';

function ReviewCard({ item, onSaved }: { item: QueryReview; onSaved: () => void }) {
  const { accessToken } = useAuth();
  const [note, setNote] = useState(item.review_note ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviewed = item.reviewed_at !== null;

  async function save() {
    if (!accessToken || busy) return;
    setBusy(true);
    setError(null);
    try {
      await adminClient.reviewQuery(item.id, note.trim() || undefined, accessToken);
      onSaved();
    } catch (err) {
      setError(errorMessage(err, 'Could not save the review.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className={`rounded-full px-2 py-0.5 font-semibold ${
            item.risk_level === 'CRITICAL' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'
          }`}
        >
          {item.risk_level}
        </span>
        {item.legal_category && (
          <span className="text-slate-500">{titleCase(item.legal_category)}</span>
        )}
        {item.jurisdiction_scope && (
          <span className="text-slate-400">· {titleCase(item.jurisdiction_scope)}</span>
        )}
        <span className="text-slate-400">
          · {item.registered ? 'Logged-in user' : 'Anonymous'} · {formatDateTime(item.created_at)}
        </span>
        {reviewed && (
          <span className="ml-auto text-emerald-700">
            Reviewed {formatDateTime(item.reviewed_at)}
          </span>
        )}
      </div>

      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-800">{item.question}</p>

      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-blue-700">
          Assistant&apos;s answer
          {item.answer_source_count !== null &&
            (item.answer_source_count === 0
              ? ' · no sources (insufficient evidence)'
              : ` · ${item.answer_source_count} source${item.answer_source_count === 1 ? '' : 's'}`)}
        </summary>
        <p className="mt-1 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-slate-700">
          {item.answer ?? 'No answer was recorded.'}
        </p>
      </details>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Review note (optional) — e.g. what was done"
          maxLength={1000}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy}
          className="rounded-lg bg-blue-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
        >
          {reviewed ? 'Update note' : 'Mark reviewed'}
        </button>
      </div>
      {error && <p className="mt-1 text-xs text-rose-600">{error}</p>}
    </li>
  );
}

export default function ReviewsPage() {
  const [status, setStatus] = useState('pending');
  const [risk, setRisk] = useState('');
  const load = useCallback(
    (token: string) => adminClient.reviews(token, { status, riskLevel: risk || undefined }),
    [status, risk],
  );
  const { data, error, reload } = useAdminData(load);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectCls}>
          <option value="pending">Awaiting review</option>
          <option value="reviewed">Reviewed</option>
          <option value="all">All</option>
        </select>
        <select value={risk} onChange={(e) => setRisk(e.target.value)} className={selectCls}>
          <option value="">Any risk</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
        </select>
        {data && <span className="text-xs text-slate-500">{data.total} total</span>}
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Chat queries the classifier rated high or critical risk. Reviewers see the question, the
        answer and the classification — never who asked.
      </p>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      {!data && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : data && data.items.length === 0 ? (
        <p className="text-sm text-slate-500">Nothing here. 🎉</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data?.items.map((item) => (
            <ReviewCard key={`${item.id}-${item.reviewed_at}`} item={item} onSaved={reload} />
          ))}
        </ul>
      )}
    </div>
  );
}
