'use client';

import { INDIAN_STATES, LEGAL_CATEGORIES, MANDATORY_DISCLAIMER } from '@legal-platform/shared';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { titleCase } from '@/lib/format';
import {
  advocateClient,
  type AdvocateDirectoryEntry,
  type AdvocateSearchFilters,
} from '@/lib/advocate-client';

const EMPTY_FILTERS: AdvocateSearchFilters = {};

export default function AdvocatesPage() {
  const [filters, setFilters] = useState<AdvocateSearchFilters>(EMPTY_FILTERS);
  const [results, setResults] = useState<AdvocateDirectoryEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    advocateClient
      .search(filters)
      .then((res) => {
        if (cancelled) return;
        setResults(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiRequestError ? err.message : 'Could not load advocates. Try again.',
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  function updateFilter<K extends keyof AdvocateSearchFilters>(
    key: K,
    value: AdvocateSearchFilters[K],
  ) {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-4 py-6">
      <header className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight">Find an Advocate</h1>
        <p className="text-xs text-slate-500">
          Browse verified advocates by practice area, location and language.
        </p>
      </header>

      <div className="mb-4 grid grid-cols-2 gap-2 rounded-xl border border-slate-200 bg-white p-3 sm:grid-cols-4">
        <select
          value={filters.practice_area ?? ''}
          onChange={(e) => updateFilter('practice_area', e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
        >
          <option value="">Any practice area</option>
          {LEGAL_CATEGORIES.filter((c) => c !== 'OUT_OF_SCOPE').map((c) => (
            <option key={c} value={c}>
              {titleCase(c)}
            </option>
          ))}
        </select>
        <select
          value={filters.state_code ?? ''}
          onChange={(e) => updateFilter('state_code', e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
        >
          <option value="">Any state</option>
          {INDIAN_STATES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input
          placeholder="City"
          value={filters.city ?? ''}
          onChange={(e) => updateFilter('city', e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
        />
        <input
          placeholder="Language (e.g. hi)"
          value={filters.language ?? ''}
          onChange={(e) => updateFilter('language', e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
        />
      </div>

      {error && <p className="mb-3 text-sm text-rose-600">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-500">Loading advocates…</p>
      ) : results && results.length > 0 ? (
        <>
          <p className="mb-2 text-xs text-slate-500">{total} advocate(s) found</p>
          <ul className="flex flex-col gap-3">
            {results.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/advocates/${a.id}`}
                  className="block rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-500"
                >
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium text-slate-800">
                      {a.display_name || 'Advocate'}
                    </span>
                    {a.consultation_fee && (
                      <span className="text-xs text-slate-500">₹{a.consultation_fee}</span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {a.city}, {a.state_code}
                    {a.experience_years != null && ` · ${a.experience_years} yrs experience`}
                  </p>
                  {a.practice_areas.length > 0 && (
                    <p className="mt-1 text-xs text-slate-500">
                      {a.practice_areas.map(titleCase).join(', ')}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="text-sm text-slate-500">No advocates match those filters yet.</p>
      )}

      <p className="mt-6 text-center text-xs leading-relaxed text-slate-400">
        {MANDATORY_DISCLAIMER}
      </p>
    </main>
  );
}
