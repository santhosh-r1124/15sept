'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';

export function SiteHeader() {
  const { user, loading } = useAuth();

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-3 text-sm">
        <Link href="/" className="font-semibold tracking-tight text-slate-900">
          Legal Advisor
        </Link>
        <nav className="flex items-center gap-4">
          <Link href="/chat" className="text-slate-600 hover:text-slate-900">
            Chat
          </Link>
          <Link href="/documents" className="text-slate-600 hover:text-slate-900">
            Documents
          </Link>
          <Link href="/advocates" className="text-slate-600 hover:text-slate-900">
            Advocates
          </Link>
          {loading ? null : user ? (
            <Link href="/profile" className="text-slate-600 hover:text-slate-900">
              {user.display_name || user.email}
            </Link>
          ) : (
            <>
              <Link href="/login" className="text-slate-600 hover:text-slate-900">
                Log in
              </Link>
              <Link
                href="/register"
                className="rounded-lg bg-blue-700 px-3 py-1.5 font-medium text-white hover:bg-blue-800"
              >
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
