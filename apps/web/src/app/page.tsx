import { MANDATORY_DISCLAIMER } from '@legal-platform/shared';
import Link from 'next/link';
import { SystemStatus } from '@/components/system-status';
import { env } from '@/lib/env';

const PHASES = [
  { n: 3, label: 'Indian Legal Knowledge Base' },
  { n: 6, label: 'Legal Document Assistant' },
  { n: 7, label: 'Advocate Marketplace' },
  { n: 8, label: 'On-Demand Consultation' },
];

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-16">
      <header className="flex flex-col gap-2">
        <span className="w-fit rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
          Phase 2 · Public legal AI chat · {env.NEXT_PUBLIC_APP_ENV}
        </span>
        <h1 className="text-3xl font-semibold tracking-tight">
          Indian Legal Advisor Bot &amp; Advocate Connect
        </h1>
        <p className="text-slate-600">
          AI-grounded legal information over verified Indian sources, with a path to qualified
          advocates when a matter needs professional help.
        </p>
        <Link
          href="/chat"
          className="mt-2 w-fit rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800"
        >
          Ask a legal question →
        </Link>
      </header>

      <SystemStatus />

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-700">Coming in later phases</h2>
        <ul className="mt-3 space-y-1.5 text-sm text-slate-600">
          {PHASES.map((p) => (
            <li key={p.n} className="flex gap-2">
              <span className="font-mono text-xs text-slate-400">P{p.n}</span>
              {p.label}
            </li>
          ))}
        </ul>
      </section>

      <footer className="mt-auto border-t border-slate-200 pt-4 text-xs leading-relaxed text-slate-500">
        {MANDATORY_DISCLAIMER}
      </footer>
    </main>
  );
}
