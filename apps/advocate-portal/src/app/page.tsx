import { env } from '@/lib/env';

const DASHBOARD_SECTIONS = [
  "Today's Requests",
  'Upcoming Consultations',
  'Active Matters',
  'Messages',
  'Documents',
  'Earnings',
  'Availability',
];

export default function AdvocatePortalHome() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-16">
      <span className="w-fit rounded-full bg-teal-50 px-3 py-1 text-xs font-medium text-teal-700">
        Phase 0 · Advocate Portal skeleton · {env.NEXT_PUBLIC_APP_ENV}
      </span>
      <h1 className="text-2xl font-semibold tracking-tight">Advocate Portal</h1>
      <p className="text-slate-600">
        The operating surface advocates use to accept requests, run consultations, exchange
        documents and track earnings. Built out in Phase 9.
      </p>
      <ul className="grid grid-cols-2 gap-2 text-sm">
        {DASHBOARD_SECTIONS.map((s) => (
          <li
            key={s}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-500"
          >
            {s}
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-400">
        API base: <code>{env.NEXT_PUBLIC_API_BASE_URL}</code>
      </p>
    </main>
  );
}
