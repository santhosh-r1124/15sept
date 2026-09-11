'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { buttonClass, Field, inputClass, secondaryButtonClass } from '@/components/form';
import { ApiRequestError } from '@/lib/api-client';
import { authClient } from '@/lib/auth-client';
import { useAuth } from '@/lib/auth-context';

export default function ProfilePage() {
  const router = useRouter();
  const { user, loading, logout, updateProfile, refreshUser } = useAuth();

  const [displayName, setDisplayName] = useState('');
  const [stateCode, setStateCode] = useState('');
  const [preferredLanguage, setPreferredLanguage] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendStatus, setResendStatus] = useState<'idle' | 'sending' | 'sent'>('idle');

  useEffect(() => {
    if (!loading && !user) router.replace('/login');
  }, [loading, user, router]);

  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name ?? '');
      setStateCode(user.state_code ?? '');
      setPreferredLanguage(user.preferred_language ?? '');
    }
  }, [user]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      await updateProfile({
        display_name: displayName || undefined,
        state_code: stateCode || undefined,
        preferred_language: preferredLanguage || undefined,
      });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Could not save your profile.');
    } finally {
      setSaving(false);
    }
  }

  async function onResendVerification() {
    if (!user) return;
    setResendStatus('sending');
    try {
      await authClient.resendVerification(user.email);
    } finally {
      setResendStatus('sent');
    }
  }

  async function onLogout() {
    await logout();
    router.push('/');
  }

  if (loading || !user) {
    return <main className="flex min-h-screen items-center justify-center text-slate-500">Loading…</main>;
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col gap-6 px-6 py-16">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Your profile</h1>
          <p className="mt-1 text-sm text-slate-600">{user.email}</p>
        </div>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
          {user.role}
        </span>
      </div>

      {!user.email_verified && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <p>Your email isn&apos;t verified yet.</p>
          <button
            type="button"
            onClick={onResendVerification}
            disabled={resendStatus !== 'idle'}
            className="mt-1 font-medium underline underline-offset-2 disabled:no-underline"
          >
            {resendStatus === 'sent' ? 'Verification email sent' : 'Resend verification email'}
          </button>
        </div>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Name">
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="State" hint="Two-letter code, e.g. KA, MH, DL.">
          <input
            type="text"
            maxLength={2}
            value={stateCode}
            onChange={(e) => setStateCode(e.target.value.toUpperCase())}
            className={inputClass}
          />
        </Field>
        <Field label="Preferred language" hint="e.g. en, hi, kn.">
          <input
            type="text"
            value={preferredLanguage}
            onChange={(e) => setPreferredLanguage(e.target.value)}
            className={inputClass}
          />
        </Field>

        {error && <p className="text-sm text-rose-600">{error}</p>}
        {saved && <p className="text-sm text-emerald-600">Saved.</p>}

        <div className="flex gap-3">
          <button type="submit" disabled={saving} className={buttonClass}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          <button
            type="button"
            onClick={() => void refreshUser()}
            className={secondaryButtonClass}
          >
            Refresh
          </button>
        </div>
      </form>

      <button type="button" onClick={() => void onLogout()} className={`${secondaryButtonClass} mt-auto`}>
        Log out
      </button>
    </main>
  );
}
