'use client';

import { hasAdminAccess } from '@legal-platform/shared';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useAuth } from '@/lib/auth-context';

const TABS = [
  { href: '/admin', label: 'Overview' },
  { href: '/admin/reviews', label: 'Risk review' },
  { href: '/admin/advocates', label: 'Advocates' },
  { href: '/admin/users', label: 'Users' },
  { href: '/admin/matters', label: 'Matters' },
  { href: '/admin/payments', label: 'Payments' },
  { href: '/admin/sources', label: 'Legal sources' },
];

/**
 * Role gate for everything under /admin. This only decides what to *show*: every admin API
 * call is authorised again on the server, so a user who edits this check gets empty pages
 * and 403s, not data.
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();

  if (loading) return <main className="mx-auto max-w-5xl px-4 py-6 text-sm">Loading…</main>;
  if (!user) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-6 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-blue-700 hover:underline">
          Log in
        </Link>{' '}
        with an admin account to continue.
      </main>
    );
  }
  if (!hasAdminAccess(user.role)) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-6 text-sm text-slate-600">
        This area is for platform administrators.
      </main>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Admin &amp; legal ops</h1>
      <nav className="mt-3 flex flex-wrap gap-1 border-b border-slate-200 text-sm">
        {TABS.map((tab) => {
          const active = tab.href === '/admin' ? pathname === '/admin' : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`-mb-px rounded-t-md border-b-2 px-3 py-2 ${
                active
                  ? 'border-blue-700 font-medium text-blue-800'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-5">{children}</div>
    </div>
  );
}
