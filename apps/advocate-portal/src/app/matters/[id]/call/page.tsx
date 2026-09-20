'use client';

import Link from 'next/link';
import { use, useEffect, useState } from 'react';
import { CallRoom } from '@/components/call-room';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { portalClient, type MatterOut } from '@/lib/portal-client';

export default function CallPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, accessToken, loading } = useAuth();
  const [matter, setMatter] = useState<MatterOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    portalClient
      .getMatter(id, accessToken)
      .then((m) => !cancelled && setMatter(m))
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiRequestError && err.status === 404
              ? 'This matter could not be found.'
              : 'Could not load this matter.',
          );
      });
    return () => {
      cancelled = true;
    };
  }, [id, accessToken]);

  if (loading) return <main className="mx-auto max-w-3xl px-6 py-8 text-sm">Loading…</main>;
  if (!user || !accessToken) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-teal-700 hover:underline">
          Log in
        </Link>{' '}
        to join your consultation.
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-6">
      {matter && <h1 className="text-lg font-semibold tracking-tight">{matter.title}</h1>}
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {matter && (
        <CallRoom
          matterId={id}
          token={accessToken}
          backHref={`/matters/${id}`}
          counterpart={matter.consumer.display_name ?? 'the client'}
        />
      )}
    </main>
  );
}
