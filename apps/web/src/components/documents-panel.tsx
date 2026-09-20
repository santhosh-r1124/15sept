'use client';

import { useRef, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { formatBytes } from '@/lib/format';
import { matterClient, type MatterDocumentsOut, type MatterFileOut } from '@/lib/matter-client';

/**
 * The client's side of document exchange: see what the advocate has asked for, send it,
 * and download the advocate's files (including the final deliverable).
 */
export function DocumentsPanel({
  matterId,
  token,
  docs,
  canExchange,
  onChanged,
}: {
  matterId: string;
  token: string;
  docs: MatterDocumentsOut;
  /** Documents change hands only after the advocate accepts, and until the matter ends. */
  canExchange: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<string>('');
  const fileInput = useRef<HTMLInputElement | null>(null);
  const openRequests = docs.requests.filter((r) => r.status === 'OPEN');

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'That did not work. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function upload() {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    await run(async () => {
      await matterClient.uploadFile(matterId, file, token, target ? { requestId: target } : {});
      if (fileInput.current) fileInput.current.value = '';
      setTarget('');
    });
  }

  const download = (file: MatterFileOut) =>
    run(() => matterClient.downloadFile(matterId, file, token));

  if (!canExchange && docs.files.length === 0 && docs.requests.length === 0) return null;

  return (
    <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Documents</h2>

      {openRequests.length > 0 && (
        <p className="mb-3 rounded-lg bg-amber-50 p-2 text-sm text-amber-900">
          Your advocate has asked for:{' '}
          {openRequests.map((r) => r.description).join(' · ')}
        </p>
      )}

      {docs.files.length === 0 ? (
        <p className="text-sm text-slate-400">No files yet.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-slate-100 text-sm">
          {docs.files.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-2 py-2">
              <span className="text-slate-800">
                {f.file_name}{' '}
                <span className="text-xs text-slate-400">
                  {formatBytes(f.size_bytes)} · from {f.uploader_role === 'ADVOCATE' ? 'advocate' : 'you'}
                  {f.is_final ? ' · final document' : ''}
                </span>
              </span>
              <button
                type="button"
                onClick={() => void download(f)}
                disabled={busy}
                className="text-xs font-medium text-blue-700 hover:underline disabled:opacity-60"
              >
                Download
              </button>
            </li>
          ))}
        </ul>
      )}

      {canExchange && (
        <div className="mt-4 flex flex-col gap-2 border-t border-slate-100 pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.txt"
              className="text-xs"
            />
            {openRequests.length > 0 && (
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                className="rounded-lg border border-slate-300 px-2 py-1 text-xs"
              >
                <option value="">Not for a specific request</option>
                {openRequests.map((r) => (
                  <option key={r.id} value={r.id}>
                    For: {r.description.slice(0, 40)}
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => void upload()}
              className="rounded-lg bg-blue-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
            >
              Upload
            </button>
          </div>
          <p className="text-xs text-slate-400">PDF, Word, PNG, JPEG or text — up to 10 MB.</p>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
    </section>
  );
}
