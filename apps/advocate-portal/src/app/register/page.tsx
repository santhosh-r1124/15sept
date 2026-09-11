'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { buttonClass, Field, inputClass } from '@/components/form';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';

function splitList(value: string): string[] | undefined {
  const items = value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  return items.length > 0 ? items : undefined;
}

export default function RegisterPage() {
  const router = useRouter();
  const { registerAdvocate } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [stateCode, setStateCode] = useState('');
  const [city, setCity] = useState('');
  const [practiceAreas, setPracticeAreas] = useState('');
  const [languages, setLanguages] = useState('');
  const [consultationFee, setConsultationFee] = useState('');
  const [experienceYears, setExperienceYears] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await registerAdvocate({
        email,
        password,
        display_name: displayName,
        state_code: stateCode,
        city,
        practice_areas: splitList(practiceAreas),
        languages: splitList(languages),
        consultation_fee: consultationFee || undefined,
        experience_years: experienceYears ? Number(experienceYears) : undefined,
      });
      router.push('/profile');
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Something went wrong. Try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-6 py-16">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Register as an advocate</h1>
        <p className="mt-1 text-sm text-slate-600">
          Your profile is reviewed before it goes live — you&apos;ll see the status on your
          dashboard.
        </p>
      </div>

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
        <Field label="Password" hint="At least 8 characters.">
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
        <Field label="Full name">
          <input
            type="text"
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={inputClass}
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="State" hint="e.g. KA">
            <input
              type="text"
              required
              maxLength={2}
              value={stateCode}
              onChange={(e) => setStateCode(e.target.value.toUpperCase())}
              className={inputClass}
            />
          </Field>
          <Field label="City">
            <input
              type="text"
              required
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className={inputClass}
            />
          </Field>
        </div>
        <Field label="Practice areas" hint="Comma-separated, e.g. IT_LAW, CONTRACT_LAW">
          <input
            type="text"
            value={practiceAreas}
            onChange={(e) => setPracticeAreas(e.target.value)}
            className={inputClass}
          />
        </Field>
        <Field label="Languages" hint="Comma-separated, e.g. en, hi, kn">
          <input
            type="text"
            value={languages}
            onChange={(e) => setLanguages(e.target.value)}
            className={inputClass}
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
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
          <Field label="Years of experience">
            <input
              type="number"
              min={0}
              max={70}
              value={experienceYears}
              onChange={(e) => setExperienceYears(e.target.value)}
              className={inputClass}
            />
          </Field>
        </div>

        {error && <p className="text-sm text-rose-600">{error}</p>}

        <button type="submit" disabled={submitting} className={buttonClass}>
          {submitting ? 'Registering…' : 'Register'}
        </button>
      </form>

      <p className="text-center text-sm text-slate-600">
        Already registered?{' '}
        <Link href="/login" className="font-medium text-teal-700 hover:underline">
          Log in
        </Link>
      </p>
    </main>
  );
}
