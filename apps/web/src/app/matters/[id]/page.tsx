'use client';

import { isTerminalMatterStatus, MANDATORY_DISCLAIMER } from '@legal-platform/shared';
import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, formatInr, titleCase } from '@/lib/format';
import { matterClient, type MatterMessageOut, type MatterOut } from '@/lib/matter-client';

const POLL_MS = 10_000;

export default function MatterPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, accessToken, loading: authLoading } = useAuth();
  const [matter, setMatter] = useState<MatterOut | null>(null);
  const [messages, setMessages] = useState<MatterMessageOut[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [m, msgs] = await Promise.all([
        matterClient.get(id, accessToken),
        matterClient.messages(id, accessToken),
      ]);
      setMatter(m);
      setMessages(msgs);
    } catch (err) {
      setError(
        err instanceof ApiRequestError && err.status === 404
          ? 'This matter could not be found.'
          : 'Could not load this matter.',
      );
    }
  }, [id, accessToken]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  async function act(action: 'pay' | 'cancel') {
    if (!accessToken || busy) return;
    setBusy(true);
    setError(null);
    try {
      setMatter(await matterClient.act(id, action, accessToken));
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'That did not work. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    const body = draft.trim();
    if (!accessToken || !body || busy) return;
    setBusy(true);
    try {
      const sent = await matterClient.postMessage(id, body, accessToken);
      setMessages((prev) => [...prev, sent]);
      setDraft('');
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Could not send the message.');
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) return <main className="mx-auto max-w-2xl px-4 py-6 text-sm">Loading…</main>;
  if (!user) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-6 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-blue-700 hover:underline">
          Log in
        </Link>{' '}
        to view this matter.
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-6">
      <Link href="/matters" className="mb-4 w-fit text-xs text-slate-500 hover:text-slate-900">
        ← My matters
      </Link>
      {error && <p className="mb-3 text-sm text-rose-600">{error}</p>}
      {!matter ? (
        !error && <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <>
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex items-baseline justify-between gap-2">
              <h1 className="text-lg font-semibold tracking-tight">{matter.title}</h1>
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                {titleCase(matter.status)}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {titleCase(matter.service_type)}
              {matter.consultation_minutes ? ` · ${matter.consultation_minutes} min` : ''} ·{' '}
              {matter.advocate.display_name ?? 'Advocate'}
            </p>
            <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700">{matter.requirement}</p>

            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs text-slate-400">Fee</dt>
                <dd className="text-slate-700">{formatInr(matter.quoted_fee)}</dd>
              </div>
              {matter.scheduled_at && (
                <div>
                  <dt className="text-xs text-slate-400">Scheduled</dt>
                  <dd className="text-slate-700">{formatDateTime(matter.scheduled_at)}</dd>
                </div>
              )}
              {matter.decision_note && (
                <div className="col-span-2">
                  <dt className="text-xs text-slate-400">Advocate note</dt>
                  <dd className="text-slate-700">{matter.decision_note}</dd>
                </div>
              )}
            </dl>

            {user.role !== 'ADVOCATE' && (
              <div className="mt-4 flex gap-2">
                {matter.status === 'ACCEPTED' && (
                  <button
                    type="button"
                    onClick={() => void act('pay')}
                    disabled={busy}
                    className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
                  >
                    Pay {formatInr(matter.quoted_fee)}
                  </button>
                )}
                {(matter.status === 'REQUESTED' || matter.status === 'ACCEPTED') && (
                  <button
                    type="button"
                    onClick={() => void act('cancel')}
                    disabled={busy}
                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                  >
                    Cancel
                  </button>
                )}
              </div>
            )}
            {matter.status === 'REQUESTED' && (
              <p className="mt-3 text-xs text-slate-400">
                Waiting for the advocate to review your request and send a quote.
              </p>
            )}
          </div>

          <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
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
                        ? 'self-start bg-slate-100 text-slate-800'
                        : 'self-end bg-blue-700 text-white'
                    }`}
                  >
                    {m.body}
                  </li>
                ))}
              </ul>
            )}
            {!isTerminalMatterStatus(matter.status) ? (
              <div className="mt-3 flex gap-2">
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void send()}
                  placeholder="Write a message…"
                  maxLength={4000}
                  className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
                <button
                  type="button"
                  onClick={() => void send()}
                  disabled={busy || !draft.trim()}
                  className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-60"
                >
                  Send
                </button>
              </div>
            ) : (
              <p className="mt-3 text-xs text-slate-400">This matter has ended; the thread is read-only.</p>
            )}
          </section>
        </>
      )}
      <p className="mt-6 text-center text-xs leading-relaxed text-slate-400">{MANDATORY_DISCLAIMER}</p>
    </main>
  );
}
