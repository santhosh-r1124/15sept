'use client';

import {
  formatCallDuration,
  type CallStatus,
  type MatterServiceType,
  type MatterStatus,
} from '@legal-platform/shared';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { callClient } from '@/lib/call-client';
import { formatDateTime } from '@/lib/format';

// A room exists for a paid consultation; after it closes only the history is shown.
const SHOWN: MatterStatus[] = ['PAID', 'SCHEDULED', 'CLOSED'];

/** The consultation call on a matter page: is the room open, who is in it, past calls. */
export function CallCard({
  matterId,
  token,
  status,
  serviceType,
  counterpart,
}: {
  matterId: string;
  token: string;
  status: MatterStatus;
  serviceType: MatterServiceType;
  counterpart: string;
}) {
  const [info, setInfo] = useState<CallStatus | null>(null);
  const relevant = serviceType === 'CONSULTATION' && SHOWN.includes(status);

  useEffect(() => {
    if (!relevant) return;
    let cancelled = false;
    const load = () =>
      callClient
        .status(matterId, token)
        .then((s) => !cancelled && setInfo(s))
        .catch(() => undefined);
    void load();
    const timer = setInterval(load, 10_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [relevant, matterId, token, status]);

  if (!relevant || !info) return null;
  const { access, present, calls } = info;
  const waiting = present.length > 0;
  if (!access.allowed && calls.length === 0) {
    // Nothing to join and nothing happened; a scheduled room still says when it opens.
    if (access.reason !== 'too_early') return null;
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">Video / voice consultation</h2>
      {access.allowed ? (
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href={`/matters/${matterId}/call`}
            className="rounded-lg bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800"
          >
            {waiting ? 'Join now' : 'Open consultation room'}
          </Link>
          <span className="text-slate-600">
            {waiting ? `${counterpart} is in the room.` : 'No one is in the room yet.'}
          </span>
        </div>
      ) : access.reason === 'too_early' ? (
        <p className="text-slate-600">Opens {formatDateTime(access.opens_at)}.</p>
      ) : (
        <p className="text-slate-500">The consultation room is closed.</p>
      )}

      {calls.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
          {calls.map((c) => (
            <li key={c.id}>
              {formatDateTime(c.opened_at)} ·{' '}
              {c.duration_seconds !== null
                ? `${formatCallDuration(c.duration_seconds)} together`
                : 'the other person didn’t join'}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
