'use client';

import { useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { portalClient, type MatterMessageOut } from '@/lib/portal-client';

/** The matter's message thread from the advocate's side. */
export function MessagesPanel({
  matterId,
  token,
  messages,
  onSent,
  readOnly,
}: {
  matterId: string;
  token: string;
  messages: MatterMessageOut[];
  onSent: (message: MatterMessageOut) => void;
  readOnly: boolean;
}) {
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const body = draft.trim();
    if (!body || busy) return;
    setBusy(true);
    setError(null);
    try {
      onSent(await portalClient.postMessage(matterId, body, token));
      setDraft('');
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Could not send the message.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Messages</h2>
      {messages.length === 0 ? (
        <p className="text-sm text-slate-400">No messages yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {messages.map((m) => (
            <li
              key={m.id}
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                m.sender_role === 'ADVOCATE'
                  ? 'self-end bg-teal-700 text-white'
                  : 'self-start bg-slate-100 text-slate-800'
              }`}
            >
              {m.body}
            </li>
          ))}
        </ul>
      )}
      {readOnly ? (
        <p className="mt-3 text-xs text-slate-400">This matter has ended; the thread is read-only.</p>
      ) : (
        <div className="mt-3 flex flex-col gap-2">
          <div className="flex gap-2">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void send()}
              placeholder="Reply to the client…"
              maxLength={4000}
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-600"
            />
            <button
              type="button"
              onClick={() => void send()}
              disabled={busy || !draft.trim()}
              className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
            >
              Send
            </button>
          </div>
          {error && <p className="text-xs text-rose-600">{error}</p>}
        </div>
      )}
    </section>
  );
}
