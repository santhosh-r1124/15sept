'use client';

import { MANDATORY_DISCLAIMER } from '@legal-platform/shared';
import { useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import {
  documentClient,
  type DocumentTypeInfoOut,
  type QuestionOut,
} from '@/lib/document-client';

// Acronyms that should stay all-caps rather than being title-cased.
const ACRONYMS = new Set(['NDA']);

function formatTypeLabel(documentType: string): string {
  return documentType
    .split('_')
    .map((w) => (ACRONYMS.has(w) ? w : w[0] + w.slice(1).toLowerCase()))
    .join(' ');
}

export default function DocumentsPage() {
  const { accessToken } = useAuth();
  const [types, setTypes] = useState<DocumentTypeInfoOut[] | null>(null);
  const [typesError, setTypesError] = useState<string | null>(null);
  const [selected, setSelected] = useState<DocumentTypeInfoOut | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ text: string; disclaimer: string } | null>(null);

  useEffect(() => {
    documentClient
      .listTypes()
      .then(setTypes)
      .catch(() => setTypesError('Could not load document types. Try refreshing the page.'));
  }, []);

  function selectType(info: DocumentTypeInfoOut) {
    setSelected(info);
    setAnswers({});
    setDraft(null);
    setSubmitError(null);
  }

  function reset() {
    setSelected(null);
    setAnswers({});
    setDraft(null);
    setSubmitError(null);
  }

  const missingRequired =
    selected?.questions.filter((q) => q.required && !(answers[q.key] || '').trim()) ?? [];

  async function handleSubmit() {
    if (!selected || missingRequired.length > 0 || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await documentClient.create(selected.document_type, answers, accessToken);
      setDraft({ text: res.document.draft_text, disclaimer: res.disclaimer });
    } catch (err) {
      setSubmitError(
        err instanceof ApiRequestError ? err.message : 'Could not generate the draft. Try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-6">
      <header className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight">Document Assistant</h1>
        <p className="text-xs text-slate-500">
          Answer a few questions and get a draft, plus notes on what's normally required.
        </p>
      </header>

      {draft ? (
        <section className="flex flex-col gap-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Your draft</h2>
            <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800">{draft.text}</pre>
          </div>
          <p className="text-xs leading-relaxed text-slate-500">{draft.disclaimer}</p>
          <button
            type="button"
            onClick={reset}
            className="w-fit rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Start another document
          </button>
        </section>
      ) : selected ? (
        <section className="flex flex-col gap-4">
          <button
            type="button"
            onClick={() => setSelected(null)}
            className="w-fit text-xs text-slate-500 hover:text-slate-900"
          >
            ← Choose a different document type
          </button>
          <h2 className="text-sm font-semibold text-slate-700">
            {formatTypeLabel(selected.document_type)}
          </h2>
          <div className="flex flex-col gap-3">
            {selected.questions.map((q: QuestionOut) => (
              <label key={q.key} className="flex flex-col gap-1 text-sm">
                <span className="font-medium text-slate-700">
                  {q.label}
                  {!q.required && <span className="ml-1 font-normal text-slate-400">(optional)</span>}
                </span>
                {q.help_text && <span className="text-xs text-slate-500">{q.help_text}</span>}
                <textarea
                  value={answers[q.key] ?? ''}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [q.key]: e.target.value }))}
                  rows={2}
                  className="resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </label>
            ))}
          </div>
          {submitError && <p className="text-sm text-rose-600">{submitError}</p>}
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting || missingRequired.length > 0}
            className="w-fit rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? 'Generating…' : 'Generate draft'}
          </button>
        </section>
      ) : (
        <section>
          {typesError && <p className="text-sm text-rose-600">{typesError}</p>}
          {types === null && !typesError ? (
            <p className="text-sm text-slate-500">Loading document types…</p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {types?.map((info) => (
                <button
                  key={info.document_type}
                  type="button"
                  onClick={() => selectType(info)}
                  className="rounded-lg border border-slate-300 px-3 py-3 text-left text-sm text-slate-700 hover:border-blue-500 hover:text-blue-700"
                >
                  {formatTypeLabel(info.document_type)}
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      <p className="mt-6 text-center text-xs leading-relaxed text-slate-400">
        {MANDATORY_DISCLAIMER}
      </p>
    </main>
  );
}
