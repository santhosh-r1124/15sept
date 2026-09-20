'use client';

import { CONSULTATION_MINUTES, MATTER_SERVICE_TYPES, type MatterServiceType } from '@legal-platform/shared';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { titleCase } from '@/lib/format';
import { matterClient } from '@/lib/matter-client';

/** "Book this advocate" — sits on the public advocate profile (Phase 8). */
export function BookingForm({ advocateId }: { advocateId: string }) {
  const { user, accessToken, loading } = useAuth();
  const router = useRouter();
  const [serviceType, setServiceType] = useState<MatterServiceType>('CONSULTATION');
  const [minutes, setMinutes] = useState<number>(30);
  const [title, setTitle] = useState('');
  const [requirement, setRequirement] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading) return null;
  if (!user || !accessToken) {
    return (
      <p className="mt-6 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-blue-700 hover:underline">
          Log in
        </Link>{' '}
        or{' '}
        <Link href="/register" className="font-medium text-blue-700 hover:underline">
          create an account
        </Link>{' '}
        to book this advocate.
      </p>
    );
  }
  if (user.role === 'ADVOCATE') return null;

  async function submit() {
    if (!accessToken || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const matter = await matterClient.create(
        {
          advocate_id: advocateId,
          service_type: serviceType,
          ...(serviceType === 'CONSULTATION' ? { consultation_minutes: minutes } : {}),
          title: title.trim(),
          requirement: requirement.trim(),
        },
        accessToken,
      );
      router.push(`/matters/${matter.id}`);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Could not send the request.');
      setSubmitting(false);
    }
  }

  const ready = title.trim().length > 0 && requirement.trim().length > 0;
  return (
    <div className="mt-6 flex flex-col gap-3 border-t border-slate-200 pt-5">
      <h2 className="text-sm font-semibold text-slate-700">Request this advocate</h2>
      <div className="flex gap-2">
        <select
          value={serviceType}
          onChange={(e) => setServiceType(e.target.value as MatterServiceType)}
          className="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
        >
          {MATTER_SERVICE_TYPES.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </select>
        {serviceType === 'CONSULTATION' && (
          <select
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
            className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          >
            {CONSULTATION_MINUTES.map((m) => (
              <option key={m} value={m}>
                {m} min
              </option>
            ))}
          </select>
        )}
      </div>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Matter title, e.g. Rental agreement review"
        maxLength={200}
        className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />
      <textarea
        value={requirement}
        onChange={(e) => setRequirement(e.target.value)}
        placeholder="What do you need help with?"
        rows={3}
        maxLength={4000}
        className="resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm"
      />
      {error && <p className="text-sm text-rose-600">{error}</p>}
      <button
        type="button"
        onClick={() => void submit()}
        disabled={!ready || submitting}
        className="w-fit rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? 'Sending…' : 'Send request'}
      </button>
      <p className="text-xs text-slate-400">
        The advocate reviews your request and sends a fee quote; you only pay once you accept it.
      </p>
    </div>
  );
}
