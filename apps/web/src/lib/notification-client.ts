import { apiFetch } from './api-client';

export interface NotificationOut {
  id: string;
  kind: string;
  title: string;
  body: string;
  /** Relative path inside this app, e.g. "/matters/<id>"; null when there is nowhere to go. */
  link: string | null;
  read: boolean;
  created_at: string;
}

export interface PaginatedNotifications {
  items: NotificationOut[];
  total: number;
  unread: number;
  limit: number;
  offset: number;
}

export interface NotificationPreferences {
  email_notifications: boolean;
}

const base = '/api/v1/notifications';

/** Bindings for `/api/v1/notifications/*`. */
export const notificationClient = {
  list: (token: string, opts: { unreadOnly?: boolean; limit?: number } = {}) =>
    apiFetch<PaginatedNotifications>(
      `${base}?limit=${opts.limit ?? 50}${opts.unreadOnly ? '&unread_only=true' : ''}`,
      { token },
    ),

  unreadCount: (token: string) => apiFetch<{ unread: number }>(`${base}/unread-count`, { token }),

  markRead: (id: string, token: string) =>
    apiFetch<NotificationOut>(`${base}/${id}/read`, { method: 'POST', token }),

  markAllRead: (token: string) =>
    apiFetch<{ updated: number }>(`${base}/read-all`, { method: 'POST', token }),

  preferences: (token: string) => apiFetch<NotificationPreferences>(`${base}/preferences`, { token }),

  setPreferences: (prefs: NotificationPreferences, token: string) =>
    apiFetch<NotificationPreferences>(`${base}/preferences`, {
      method: 'PUT',
      body: prefs,
      token,
    }),
};

/** Tells the header bell to re-read its count right away (it otherwise polls). */
export const NOTIFICATIONS_CHANGED = 'notifications-changed';
