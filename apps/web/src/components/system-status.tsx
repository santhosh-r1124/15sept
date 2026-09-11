'use client';

import { useEffect, useState } from 'react';

type Status = 'loading' | 'ok' | 'degraded' | 'error';

interface Health {
  status: Status;
  detail: string;
  checks?: Record<string, { status: string }>;
}

const DOT: Record<Status, string> = {
  loading: 'bg-slate-300',
  ok: 'bg-emerald-500',
  degraded: 'bg-amber-500',
  error: 'bg-rose-500',
};

/**
 * Calls the local `/api/health` route (which proxies the FastAPI backend) and
 * shows a live status pill. Phase 0 proof that web -> api -> db/redis is wired.
 */
export function SystemStatus() {
  const [health, setHealth] = useState<Health>({ status: 'loading', detail: 'Checking…' });

  useEffect(() => {
    let cancelled = false;
    fetch('/api/health')
      .then((r) => r.json())
      .then((data: Health) => {
        if (!cancelled) setHealth(data);
      })
      .catch(() => {
        if (!cancelled) setHealth({ status: 'error', detail: 'Status route unreachable' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <div className="flex items-center gap-2 font-medium">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${DOT[health.status]}`} />
        Platform status: {health.status}
      </div>
      <p className="mt-1 text-slate-500">{health.detail}</p>
      {health.checks && (
        <ul className="mt-3 grid grid-cols-2 gap-1 text-xs text-slate-500">
          {Object.entries(health.checks).map(([name, c]) => (
            <li key={name} className="flex items-center gap-1.5">
              <span
                className={`inline-block h-2 w-2 rounded-full ${
                  c.status === 'ok' ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
              {name}: {c.status}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
