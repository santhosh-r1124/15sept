'use client';

import Link from 'next/link';
import { NotificationBell } from '@/components/notification-bell';
import { useAuth } from '@/lib/auth-context';

export function SiteHeader() {
  const { user, loading } = useAuth();

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-3 text-sm">
        <Link href="/" className="font-semibold tracking-tight text-slate-900">
          Advocate Portal
        </Link>
        <nav className="flex items-center gap-4">
          {loading ? null : user ? (
            <>
              <Link href="/" className="text-slate-600 hover:text-slate-900">
                Dashboard
              </Link>
              <Link href="/matters" className="text-slate-600 hover:text-slate-900">
                Matters
              </Link>
              <Link href="/earnings" className="text-slate-600 hover:text-slate-900">
                Earnings
              </Link>
              <NotificationBell />
              <Link href="/profile" className="text-slate-600 hover:text-slate-900">
                {user.display_name || user.email}
              </Link>
            </>
          ) : (
            <>
              <Link href="/login" className="text-slate-600 hover:text-slate-900">
                Log in
              </Link>
              <Link
                href="/register"
                className="rounded-lg bg-teal-700 px-3 py-1.5 font-medium text-white hover:bg-teal-800"
              >
                Register
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
