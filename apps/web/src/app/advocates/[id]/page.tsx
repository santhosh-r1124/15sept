'use client';

import { MANDATORY_DISCLAIMER } from '@legal-platform/shared';
import Link from 'next/link';
import { use, useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { advocateClient, type AdvocateDirectoryEntry } from '@/lib/advocate-client';

function formatCategoryLabel(category: string): string {
  return category
    .split('_')
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(' ');
}

export default function AdvocateProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [advocate, setAdvocate] = useState<AdvocateDirectoryEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    advocateClient
      .get(id)
      .then((res) => {
        if (!cancelled) setAdvocate(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiRequestError && err.status === 404
            ? 'This advocate could not be found.'
            : 'Could not load this advocate. Try again.',
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-6">
      <Link href="/advocates" className="mb-4 w-fit text-xs text-slate-500 hover:text-slate-900">
        ← Back to search
      </Link>

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : error || !advocate ? (
        <p className="text-sm text-rose-600">{error || 'Advocate not found.'}</p>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex items-baseline justify-between">
            <h1 className="text-xl font-semibold tracking-tight">
              {advocate.display_name || 'Advocate'}
            </h1>
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
              Verified
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {advocate.city}, {advocate.state_code}
          </p>

          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            {advocate.experience_years != null && (
              <div>
                <dt className="text-xs text-slate-400">Experience</dt>
                <dd className="text-slate-700">{advocate.experience_years} years</dd>
              </div>
            )}
            {advocate.consultation_fee && (
              <div>
                <dt className="text-xs text-slate-400">Consultation fee</dt>
                <dd className="text-slate-700">₹{advocate.consultation_fee}</dd>
              </div>
            )}
            {advocate.languages.length > 0 && (
              <div>
                <dt className="text-xs text-slate-400">Languages</dt>
                <dd className="text-slate-700">{advocate.languages.join(', ')}</dd>
              </div>
            )}
            {advocate.practice_areas.length > 0 && (
              <div>
                <dt className="text-xs text-slate-400">Practice areas</dt>
                <dd className="text-slate-700">
                  {advocate.practice_areas.map(formatCategoryLabel).join(', ')}
                </dd>
              </div>
            )}
          </dl>

          {advocate.bio && (
            <div className="mt-4">
              <h2 className="text-xs font-medium text-slate-400">About</h2>
              <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{advocate.bio}</p>
            </div>
          )}

          <p className="mt-6 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
            On-demand consultation booking is coming soon — for now, this is a directory listing
            only.
          </p>
        </div>
      )}

      <p className="mt-6 text-center text-xs leading-relaxed text-slate-400">
        {MANDATORY_DISCLAIMER}
      </p>
    </main>
  );
}
