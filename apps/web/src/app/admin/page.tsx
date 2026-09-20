'use client';

import Link from 'next/link';
import { adminClient } from '@/lib/admin-client';
import { formatInr, titleCase } from '@/lib/format';
import { useAdminData } from '@/lib/use-admin-data';

function Breakdown({ title, counts }: { title: string; counts: Record<string, number> }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">{title}</h2>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {Object.entries(counts).map(([key, n]) => (
          <div key={key} className="flex justify-between gap-2">
            <dt className="text-slate-500">{titleCase(key)}</dt>
            <dd className={n > 0 ? 'font-medium text-slate-800' : 'text-slate-300'}>{n}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Attention({
  label,
  count,
  href,
  hint,
}: {
  label: string;
  count: number;
  href?: string;
  hint?: string;
}) {
  const hot = count > 0;
  const body = (
    <div
      className={`rounded-xl border p-4 ${
        hot ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-white'
      }`}
    >
      <div className={`text-2xl font-semibold ${hot ? 'text-amber-800' : 'text-slate-400'}`}>
        {count}
      </div>
      <div className="text-sm text-slate-700">{label}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
  return href && hot ? (
    <Link href={href} className="block hover:opacity-90">
      {body}
    </Link>
  ) : (
    body
  );
}

export default function AdminOverviewPage() {
  const { data, error } = useAdminData(adminClient.overview);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!data) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Attention
          label="High-risk queries to review"
          count={data.reviews_pending}
          href="/admin/reviews"
        />
        <Attention
          label="Advocates awaiting verification"
          count={data.advocates_pending}
          href="/admin/advocates"
        />
        <Attention
          label="Failed notification emails"
          count={data.emails_failed}
          hint="Mail server trouble — see the outbox"
        />
        <Attention label="Emails waiting to send" count={data.emails_pending} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Breakdown title="Users" counts={data.users_by_role} />
        <Breakdown title="Advocates" counts={data.advocates_by_status} />
        <Breakdown title="Matters" counts={data.matters_by_status} />
        <Breakdown title="Legal knowledge base" counts={data.sources_by_status} />
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Payments</h2>
        <dl className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <dt className="text-xs text-slate-400">Payments taken</dt>
            <dd className="text-lg font-medium">{data.payments.count}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">Gross</dt>
            <dd className="text-lg font-medium">{formatInr(data.payments.gross)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">Refunded</dt>
            <dd className="text-lg font-medium">{formatInr(data.payments.refunded)}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
