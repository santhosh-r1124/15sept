'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useState, type FormEvent, type ReactNode } from 'react';
import { buttonClass, Field, inputClass } from '@/components/form';
import { ApiRequestError } from '@/lib/api-client';
import { authClient } from '@/lib/auth-client';

/**
 * One page, two steps: no `?token=` shows a "send me a reset link" form; with a
 * token (from the emailed link) it shows a "set a new password" form.
 */
export function ResetPasswordClient() {
  const token = useSearchParams().get('token');
  return token ? <SetNewPassword token={token} /> : <RequestResetLink />;
}

function RequestResetLink() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await authClient.forgotPassword(email);
    } finally {
      // Always show success — the endpoint itself never reveals whether the email exists.
      setSubmitting(false);
      setSent(true);
    }
  }

  if (sent) {
    return (
      <Wrap title="Check your email">
        <p className="text-sm text-slate-600">
          If an account exists for <strong>{email}</strong>, a password reset link is on its way.
        </p>
      </Wrap>
    );
  }

  return (
    <Wrap title="Reset your password">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Email">
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
        </Field>
        <button type="submit" disabled={submitting} className={buttonClass}>
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
    </Wrap>
  );
}

function SetNewPassword({ token }: { token: string }) {
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await authClient.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : 'This link is invalid or has expired.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <Wrap title="Password updated">
        <p className="text-sm text-slate-600">You can now log in with your new password.</p>
        <Link href="/login" className={`${buttonClass} mx-auto w-fit`}>
          Log in
        </Link>
      </Wrap>
    );
  }

  return (
    <Wrap title="Choose a new password">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="New password" hint="At least 8 characters.">
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </Field>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <button type="submit" disabled={submitting} className={buttonClass}>
          {submitting ? 'Saving…' : 'Save new password'}
        </button>
      </form>
    </Wrap>
  );
}

function Wrap({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="text-left">{children}</div>
    </main>
  );
}
