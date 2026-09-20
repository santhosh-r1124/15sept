'use client';

import { isTerminalMatterStatus } from '@legal-platform/shared';
import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { CallCard } from '@/components/call-card';
import { DocumentsPanel } from '@/components/documents-panel';
import { MessagesPanel } from '@/components/messages-panel';
import { PaymentCard } from '@/components/payment-card';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime, formatInr, STATUS_STYLES, titleCase } from '@/lib/format';
import {
  portalClient,
  type MatterDocumentsOut,
  type MatterMessageOut,
  type MatterOut,
} from '@/lib/portal-client';

const POLL_MS = 10_000;
const inputCls =
  'rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-600';
const primaryBtn =
  'rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60';
const secondaryBtn =
  'rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60';

/** datetime-local gives "YYYY-MM-DDTHH:mm" in the browser's zone; the API wants an offset. */
function toIsoWithOffset(localValue: string): string {
  return new Date(localValue).toISOString();
}

export default function MatterPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, accessToken, loading: authLoading } = useAuth();
  const [matter, setMatter] = useState<MatterOut | null>(null);
  const [messages, setMessages] = useState<MatterMessageOut[]>([]);
  const [docs, setDocs] = useState<MatterDocumentsOut>({ requests: [], files: [] });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [quote, setQuote] = useState('');
  const [note, setNote] = useState('');
  const [when, setWhen] = useState('');

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [m, msgs, d] = await Promise.all([
        portalClient.getMatter(id, accessToken),
        portalClient.messages(id, accessToken),
        portalClient.documents(id, accessToken),
      ]);
      setMatter(m);
      setMessages(msgs);
      setDocs(d);
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

  useEffect(() => {
    if (matter && quote === '' && matter.status === 'REQUESTED' && matter.quoted_fee) {
      setQuote(matter.quoted_fee);
    }
  }, [matter, quote]);

  async function act(
    action: 'accept' | 'reject' | 'cancel' | 'schedule' | 'close',
    body: Record<string, unknown> = {},
  ) {
    if (!accessToken || busy) return;
    if (
      action === 'cancel' &&
      (matter?.status === 'PAID' || matter?.status === 'SCHEDULED') &&
      !window.confirm('Cancel this matter? The client will be refunded in full.')
    )
      return;
    setBusy(true);
    setError(null);
    try {
      setMatter(await portalClient.act(id, action, accessToken, body));
      setNote('');
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'That did not work. Try again.');
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) return <main className="mx-auto max-w-3xl px-6 py-8 text-sm">Loading…</main>;
  if (!user || !accessToken) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-teal-700 hover:underline">
          Log in
        </Link>{' '}
        to view this matter.
      </main>
    );
  }

  const status = matter?.status;
  const isConsultation = matter?.service_type === 'CONSULTATION';
  const needsQuote = matter !== null && matter.quoted_fee === null;

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-8">
      <Link href="/matters" className="w-fit text-xs text-slate-500 hover:text-slate-900">
        ← Matters
      </Link>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {!matter ? (
        !error && <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <>
          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex items-baseline justify-between gap-2">
              <h1 className="text-lg font-semibold tracking-tight">{matter.title}</h1>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[matter.status] ?? ''}`}
              >
                {titleCase(matter.status)}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {titleCase(matter.service_type)}
              {matter.consultation_minutes ? ` · ${matter.consultation_minutes} min` : ''} · Client:{' '}
              {matter.consumer.display_name ?? 'Anonymous'}
              {matter.consumer.verified ? ' (verified)' : ' (unverified)'}
              {matter.preferred_language ? ` · Prefers ${matter.preferred_language}` : ''}
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
                  <dt className="text-xs text-slate-400">Your note</dt>
                  <dd className="text-slate-700">{matter.decision_note}</dd>
                </div>
              )}
            </dl>

            {status === 'REQUESTED' && (
              <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4">
                <div className="flex flex-wrap items-center gap-2">
                  <label className="text-sm text-slate-600" htmlFor="quote">
                    Fee quote (₹)
                  </label>
                  <input
                    id="quote"
                    value={quote}
                    onChange={(e) => setQuote(e.target.value)}
                    inputMode="decimal"
                    placeholder={needsQuote ? 'Required' : matter.quoted_fee ?? ''}
                    className={`${inputCls} w-32`}
                  />
                  <span className="text-xs text-slate-400">
                    {needsQuote
                      ? 'Document services are quoted by you.'
                      : 'Prefilled from your fee; change it if the scope differs.'}
                  </span>
                </div>
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Note to the client (required if rejecting)"
                  maxLength={1000}
                  className={inputCls}
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    className={primaryBtn}
                    disabled={busy || (needsQuote && !quote.trim())}
                    onClick={() =>
                      void act('accept', {
                        ...(quote.trim() ? { quoted_fee: quote.trim() } : {}),
                        ...(note.trim() ? { note: note.trim() } : {}),
                      })
                    }
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    className={secondaryBtn}
                    disabled={busy || !note.trim()}
                    onClick={() => void act('reject', { note: note.trim() })}
                  >
                    Reject
                  </button>
                </div>
              </div>
            )}

            {status === 'ACCEPTED' && (
              <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-4">
                <p className="text-sm text-slate-500">Waiting for the client to pay.</p>
                <button
                  type="button"
                  className={secondaryBtn}
                  disabled={busy}
                  onClick={() => void act('cancel')}
                >
                  Cancel
                </button>
              </div>
            )}

            {(status === 'PAID' || status === 'SCHEDULED') && (
              <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4">
                {isConsultation && (
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="datetime-local"
                      value={when}
                      onChange={(e) => setWhen(e.target.value)}
                      className={inputCls}
                    />
                    <button
                      type="button"
                      className={primaryBtn}
                      disabled={busy || !when}
                      onClick={() => void act('schedule', { scheduled_at: toIsoWithOffset(when) })}
                    >
                      {status === 'SCHEDULED' ? 'Reschedule' : 'Schedule'}
                    </button>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className={secondaryBtn}
                    disabled={busy}
                    onClick={() => void act('cancel')}
                  >
                    Cancel &amp; refund client
                  </button>
                  <span className="text-xs text-slate-400">
                    Only if you can no longer deliver — the client is refunded in full.
                  </span>
                </div>
                {(status === 'SCHEDULED' || !isConsultation) && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className={secondaryBtn}
                      disabled={busy}
                      onClick={() => void act('close')}
                    >
                      Close matter
                    </button>
                    <span className="text-xs text-slate-400">
                      {isConsultation
                        ? 'After the consultation has taken place.'
                        : 'Upload the final document first, then close.'}
                    </span>
                  </div>
                )}
              </div>
            )}
          </section>

          <CallCard
            matterId={id}
            token={accessToken}
            status={matter.status}
            serviceType={matter.service_type}
            counterpart={matter.consumer.display_name ?? 'The client'}
          />
          <PaymentCard matterId={id} token={accessToken} status={matter.status} />
          <DocumentsPanel
            matterId={id}
            token={accessToken}
            docs={docs}
            canExchange={status === 'ACCEPTED' || status === 'PAID' || status === 'SCHEDULED'}
            canUploadFinal={status === 'PAID' || status === 'SCHEDULED'}
            onChanged={() => void refresh()}
          />
          <MessagesPanel
            matterId={id}
            token={accessToken}
            messages={messages}
            onSent={(m) => setMessages((prev) => [...prev, m])}
            readOnly={status !== undefined && isTerminalMatterStatus(status)}
          />
        </>
      )}
    </main>
  );
}
