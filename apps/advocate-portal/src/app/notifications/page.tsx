'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { formatDateTime } from '@/lib/format';
import {
  NOTIFICATIONS_CHANGED,
  notificationClient,
  type NotificationOut,
} from '@/lib/notification-client';

function announce() {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
}

export default function NotificationsPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const [items, setItems] = useState<NotificationOut[] | null>(null);
  const [emailOn, setEmailOn] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [feed, prefs] = await Promise.all([
        notificationClient.list(accessToken),
        notificationClient.preferences(accessToken),
      ]);
      setItems(feed.items);
      setEmailOn(prefs.email_notifications);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Could not load notifications.');
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  async function markRead(n: NotificationOut) {
    if (!accessToken || n.read) return;
    setItems((prev) => prev?.map((x) => (x.id === n.id ? { ...x, read: true } : x)) ?? prev);
    try {
      await notificationClient.markRead(n.id, accessToken);
    } catch {
      // The entry just shows as unread again on the next load.
    }
    announce();
  }

  async function markAllRead() {
    if (!accessToken) return;
    setItems((prev) => prev?.map((x) => ({ ...x, read: true })) ?? prev);
    try {
      await notificationClient.markAllRead(accessToken);
    } catch {
      setError('Could not mark everything as read.');
    }
    announce();
  }

  async function toggleEmail(next: boolean) {
    if (!accessToken) return;
    setEmailOn(next);
    try {
      await notificationClient.setPreferences({ email_notifications: next }, accessToken);
    } catch {
      setEmailOn(!next);
      setError('Could not save that preference.');
    }
  }

  if (authLoading) return <main className="mx-auto max-w-3xl px-6 py-8 text-sm">Loading…</main>;
  if (!user) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-teal-700 hover:underline">
          Log in
        </Link>{' '}
        to see your notifications.
      </main>
    );
  }

  const unread = items?.filter((n) => !n.read).length ?? 0;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-6">
      <div className="flex items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Notifications</h1>
        <button
          type="button"
          onClick={() => void markAllRead()}
          disabled={unread === 0}
          className="text-xs font-medium text-teal-700 hover:underline disabled:opacity-40 disabled:no-underline"
        >
          Mark all read
        </button>
      </div>
      <p className="mb-4 text-xs text-slate-500">Updates on your matters, payments and documents.</p>
      {error && <p className="mb-2 text-sm text-rose-600">{error}</p>}

      {items === null && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : items && items.length === 0 ? (
        <p className="text-sm text-slate-500">Nothing yet. Updates will appear here.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items?.map((n) => {
            const inner = (
              <>
                <div className="flex items-baseline justify-between gap-2">
                  <span className={`text-sm ${n.read ? 'text-slate-700' : 'font-semibold'}`}>
                    {!n.read && (
                      <span
                        className="mr-2 inline-block h-2 w-2 rounded-full bg-teal-600"
                        aria-label="Unread"
                      />
                    )}
                    {n.title}
                  </span>
                  <span className="shrink-0 text-xs text-slate-400">
                    {formatDateTime(n.created_at)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{n.body}</p>
              </>
            );
            const cls = `block rounded-xl border p-3 ${
              n.read ? 'border-slate-200 bg-white' : 'border-teal-200 bg-teal-50/40'
            }`;
            return (
              <li key={n.id}>
                {n.link ? (
                  <Link href={n.link} onClick={() => void markRead(n)} className={`${cls} hover:bg-slate-50`}>
                    {inner}
                  </Link>
                ) : (
                  <button type="button" onClick={() => void markRead(n)} className={`${cls} w-full text-left`}>
                    {inner}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {emailOn !== null && (
        <label className="mt-8 flex items-start gap-2 border-t border-slate-200 pt-4 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={emailOn}
            onChange={(e) => void toggleEmail(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Email me about these updates
            <span className="block text-xs text-slate-500">
              Emails never include matter details — just a link back here. Account emails
              (verification, password reset) are always sent.
            </span>
          </span>
        </label>
      )}
    </main>
  );
}
