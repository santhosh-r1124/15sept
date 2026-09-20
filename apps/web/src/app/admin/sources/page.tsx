'use client';

import { useState } from 'react';
import { adminClient, type LegalSource } from '@/lib/admin-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, titleCase } from '@/lib/format';
import { errorMessage, useAdminData } from '@/lib/use-admin-data';

const TYPES = ['ACT', 'RULES', 'REGULATION', 'NOTIFICATION', 'JUDGMENT', 'OTHER'];
const STATUS_STYLE: Record<string, string> = {
  COMPLETED: 'bg-emerald-100 text-emerald-800',
  FAILED: 'bg-rose-100 text-rose-800',
  PROCESSING: 'bg-sky-100 text-sky-800',
  PENDING: 'bg-amber-100 text-amber-800',
};
const inputCls = 'rounded-lg border border-slate-300 px-3 py-1.5 text-sm';

function AddSourceForm({ onAdded }: { onAdded: () => void }) {
  const { accessToken } = useAuth();
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [type, setType] = useState('ACT');
  const [lawName, setLawName] = useState('');
  const [version, setVersion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await adminClient.createSource(
        {
          title: title.trim(),
          source_url: url.trim(),
          document_type: type,
          ...(lawName.trim() ? { law_name: lawName.trim() } : {}),
          ...(version.trim() ? { version: version.trim() } : {}),
        },
        accessToken,
      );
      if (created.ingestion_status === 'FAILED') {
        setError(`Saved, but ingestion failed: ${created.ingestion_error ?? 'unknown error'}`);
      } else {
        setTitle('');
        setUrl('');
        setLawName('');
        setVersion('');
      }
      onAdded();
    } catch (err) {
      setError(errorMessage(err, 'Could not add that source.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Add a source</h2>
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title, e.g. Information Technology Act, 2000"
          className={`${inputCls} sm:col-span-2`}
        />
        <input
          required
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Source URL (an official PDF or page)"
          className={`${inputCls} sm:col-span-2`}
        />
        <select value={type} onChange={(e) => setType(e.target.value)} className={inputCls}>
          {TYPES.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </select>
        <input
          value={lawName}
          onChange={(e) => setLawName(e.target.value)}
          placeholder="Law name (optional)"
          className={inputCls}
        />
        <input
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          placeholder="Version / year (optional)"
          className={inputCls}
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-blue-700 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
        >
          {busy ? 'Fetching & indexing…' : 'Add & index'}
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        The document is downloaded, split into passages and embedded right away, which can take a
        minute for a long Act. Only official sources should go in: the assistant answers from this
        knowledge base and cites it.
      </p>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
    </form>
  );
}

export default function SourcesPage() {
  const { accessToken } = useAuth();
  const { data, error, reload } = useAdminData(adminClient.sources);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function run(source: LegalSource, action: 'reindex' | 'delete') {
    if (!accessToken || busyId) return;
    if (action === 'delete' && !window.confirm(`Remove “${source.title}” from the knowledge base?`))
      return;
    setBusyId(source.id);
    setActionError(null);
    try {
      if (action === 'reindex') await adminClient.reindexSource(source.id, accessToken);
      else await adminClient.deleteSource(source.id, accessToken);
      reload();
    } catch (err) {
      setActionError(errorMessage(err, 'That did not work.'));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <AddSourceForm onAdded={reload} />
      {(error || actionError) && <p className="text-sm text-rose-600">{error ?? actionError}</p>}
      {!data && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : data && data.items.length === 0 ? (
        <p className="text-sm text-slate-500">
          The knowledge base is empty, so chat answers will say “insufficient evidence” until sources
          are added.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data?.items.map((s) => (
            <li key={s.id} className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium text-slate-800">{s.title}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[s.ingestion_status] ?? ''}`}
                >
                  {titleCase(s.ingestion_status)}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {titleCase(s.document_type)} · {s.jurisdiction}
                {s.state_code ? `-${s.state_code}` : ''} · {s.chunk_count} passages · updated{' '}
                {formatDateTime(s.updated_at)}
              </p>
              <p className="mt-1 break-all text-xs text-slate-400">{s.source_url}</p>
              {s.ingestion_error && (
                <p className="mt-1 text-xs text-rose-600">Error: {s.ingestion_error}</p>
              )}
              <div className="mt-2 flex gap-3">
                <button
                  type="button"
                  disabled={busyId !== null}
                  onClick={() => void run(s, 'reindex')}
                  className="text-xs font-medium text-blue-700 hover:underline disabled:opacity-50"
                >
                  {busyId === s.id ? 'Working…' : 'Re-index'}
                </button>
                <button
                  type="button"
                  disabled={busyId !== null}
                  onClick={() => void run(s, 'delete')}
                  className="text-xs font-medium text-rose-700 hover:underline disabled:opacity-50"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
