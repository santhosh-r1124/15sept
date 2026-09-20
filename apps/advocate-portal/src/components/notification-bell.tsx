'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { NOTIFICATIONS_CHANGED, notificationClient } from '@/lib/notification-client';

const POLL_MS = 30_000;

/** Header link with the unread count. Polls; there is no push channel yet. */
export function NotificationBell() {
  const { accessToken } = useAuth();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    const load = () => {
      notificationClient
        .unreadCount(accessToken)
        .then((r) => !cancelled && setUnread(r.unread))
        .catch(() => {
          // A missed poll is harmless; the next one corrects the count.
        });
    };
    load();
    const timer = setInterval(load, POLL_MS);
    window.addEventListener(NOTIFICATIONS_CHANGED, load);
    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener(NOTIFICATIONS_CHANGED, load);
    };
  }, [accessToken]);

  return (
    <Link
      href="/notifications"
      className="relative text-slate-600 hover:text-slate-900"
      aria-label={unread > 0 ? `Notifications (${unread} unread)` : 'Notifications'}
    >
      Notifications
      {unread > 0 && (
        <span className="ml-1.5 rounded-full bg-rose-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </Link>
  );
}
