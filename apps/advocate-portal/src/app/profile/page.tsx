'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { buttonClass, Field, inputClass, secondaryButtonClass } from '@/components/form';
import { ApiRequestError } from '@/lib/api-client';
import { authClient } from '@/lib/auth-client';
import { useAuth } from '@/lib/auth-context';

const STATUS_STYLES: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-800',
  IN_REVIEW: 'bg-blue-100 text-blue-800',
  VERIFIED: 'bg-emerald-100 text-emerald-800',
  REJECTED: 'bg-rose-100 text-rose-800',
};

export default function ProfilePage() {
  const router = useRouter();
  const { user, profile, loading, logout, updateProfile, refresh } = useAuth();

  const [city, setCity] = useState('');
  const [stateCode, setStateCode] = useState('');
  const [practiceAreas, setPracticeAreas] = useState('');
  const [languages, setLanguages] = useState('');
  const [consultationFee, setConsultationFee] = useState('');
  const [bio, setBio] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendStatus, setResendStatus] = useState<'idle' | 'sending' | 'sent'>('idle');

  useEffect(() => {
    if (!loading && !user) router.replace('/login');
  }, [loading, user, router]);

  useEffect(() => {
    if (profile) {
      setCity(profile.city);
      setStateCode(profile.state_code);
      setPracticeAreas(profile.practice_areas.join(', '));
      setLanguages(profile.languages.join(', '));
      setConsultationFee(profile.consultation_fee ?? '');
      setBio(profile.bio ?? '');
    }
  }, [profile]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      await updateProfile({
        city,
        state_code: stateCode,
        practice_areas: practiceAreas
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        languages: languages
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        consultation_fee: consultationFee || undefined,
        bio: bio || undefined,
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

  if (loading || !user || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center text-slate-500">Loading…</main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col gap-6 px-6 py-16">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{user.display_name}</h1>
          <p className="mt-1 text-sm text-slate-600">{user.email}</p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_STYLES[profile.verification_status] ?? 'bg-slate-100 text-slate-600'}`}
        >
          {profile.verification_status.replace('_', ' ')}
        </span>
      </div>

      {profile.verification_status === 'PENDING' && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Your profile is awaiting admin verification. You can keep it updated in the meantime.
        </p>
      )}
      {profile.verification_status === 'REJECTED' && profile.verification_note && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          Rejected: {profile.verification_note}
        </p>
      )}

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
        <div className="grid grid-cols-2 gap-4">
          <Field label="State">
            <input
              type="text"
              maxLength={2}
              value={stateCode}
              onChange={(e) => setStateCode(e.target.value.toUpperCase())}
              className={inputClass}
            />
          </Field>
          <Field label="City">
            <input
              type="text"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className={inputClass}
            />
          </Field>
        </div>
        <Field label="Practice areas" hint="Comma-separated">
          <input
            type="text"
            value={practiceAreas}
            onChange={(e) => setPracticeAreas(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Languages" hint="Comma-separated">
          <input
            type="text"
            value={languages}
            onChange={(e) => setLanguages(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Consultation fee (₹)">
          <input
            type="number"
            min={0}
            step="0.01"
            value={consultationFee}
            onChange={(e) => setConsultationFee(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Bio">
          <textarea
            rows={4}
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            className={inputClass}
          />
        </Field>

        {error && <p className="text-sm text-rose-600">{error}</p>}
        {saved && <p className="text-sm text-emerald-600">Saved.</p>}

        <div className="flex gap-3">
          <button type="submit" disabled={saving} className={buttonClass}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          <button type="button" onClick={() => void refresh()} className={secondaryButtonClass}>
            Refresh
          </button>
        </div>
      </form>

      <button
        type="button"
        onClick={() => void onLogout()}
        className={`${secondaryButtonClass} mt-auto`}
      >
        Log out
      </button>
    </main>
  );
}
