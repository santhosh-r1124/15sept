'use client';

import { useRef, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { formatBytes } from '@/lib/format';
import { portalClient, type MatterDocumentsOut, type MatterFileOut } from '@/lib/portal-client';

/** Request documents from the client, upload files, and hand over the final deliverable. */
export function DocumentsPanel({
  matterId,
  token,
  docs,
  canExchange,
  canUploadFinal,
  onChanged,
}: {
  matterId: string;
  token: string;
  docs: MatterDocumentsOut;
  /** ACCEPTED / PAID / SCHEDULED: the only states in which documents change hands. */
  canExchange: boolean;
  /** PAID / SCHEDULED: the client has paid, so a final deliverable makes sense. */
  canUploadFinal: boolean;
  onChanged: () => void;
}) {
  const [description, setDescription] = useState('');
  const [isFinal, setIsFinal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

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
      await portalClient.uploadFile(matterId, file, token, { isFinal });
      if (fileInput.current) fileInput.current.value = '';
      setIsFinal(false);
    });
  }

  const download = (file: MatterFileOut) =>
    run(() => portalClient.downloadFile(matterId, file, token));

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Documents</h2>

      {docs.requests.length > 0 && (
        <ul className="mb-3 flex flex-col gap-1 text-sm">
          {docs.requests.map((r) => (
            <li key={r.id} className="flex items-baseline justify-between gap-2">
              <span className="text-slate-700">Requested: {r.description}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${
                  r.status === 'OPEN' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
                }`}
              >
                {r.status === 'OPEN' ? 'Waiting for client' : 'Received'}
              </span>
            </li>
          ))}
        </ul>
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
                  {formatBytes(f.size_bytes)} · from {f.uploader_role === 'ADVOCATE' ? 'you' : 'client'}
                  {f.is_final ? ' · final' : ''}
                </span>
              </span>
              <button
                type="button"
                onClick={() => void download(f)}
                disabled={busy}
                className="text-xs font-medium text-teal-700 hover:underline disabled:opacity-60"
              >
                Download
              </button>
            </li>
          ))}
        </ul>
      )}

      {canExchange ? (
        <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-3">
          <div className="flex gap-2">
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Ask the client for a document, e.g. ID proof"
              maxLength={1000}
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-600"
            />
            <button
              type="button"
              disabled={busy || !description.trim()}
              onClick={() =>
                void run(async () => {
                  await portalClient.requestDocument(matterId, description.trim(), token);
                  setDescription('');
                })
              }
              className="rounded-lg border border-teal-700 px-3 py-2 text-sm font-medium text-teal-700 hover:bg-teal-50 disabled:opacity-60"
            >
              Request
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.txt"
              className="text-xs"
            />
            {canUploadFinal && (
              <label className="flex items-center gap-1 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={isFinal}
                  onChange={(e) => setIsFinal(e.target.checked)}
                />
                Final deliverable
              </label>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => void upload()}
              className="rounded-lg bg-teal-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
            >
              Upload
            </button>
          </div>
          <p className="text-xs text-slate-400">PDF, Word, PNG, JPEG or text — up to 10 MB.</p>
        </div>
      ) : (
        <p className="mt-3 text-xs text-slate-400">
          Documents can be exchanged once you accept the matter, until it ends.
        </p>
      )}
      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
    </section>
  );
}
