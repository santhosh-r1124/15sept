'use client';

import { useCallback, useState } from 'react';
import { adminClient, type AdminUserRow } from '@/lib/admin-client';
import { useAuth } from '@/lib/auth-context';
import { titleCase } from '@/lib/format';
import { errorMessage, useAdminData } from '@/lib/use-admin-data';

const ROLES = ['CONSUMER', 'ADVOCATE', 'ENTERPRISE_USER', 'LEGAL_ADMIN', 'ADMIN'];

export default function UsersPage() {
  const { user: me, accessToken } = useAuth();
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [role, setRole] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(
    (token: string) => adminClient.users(token, { q: query || undefined, role: role || undefined }),
    [query, role],
  );
  const { data, error, reload } = useAdminData(load);

  async function toggle(row: AdminUserRow) {
    if (!accessToken) return;
    if (
      row.is_active &&
      !window.confirm(`Suspend ${row.email}? They will be signed out and unable to log in.`)
    )
      return;
    setActionError(null);
    try {
      await adminClient.setUserActive(row.id, !row.is_active, accessToken);
      reload();
    } catch (err) {
      setActionError(errorMessage(err, 'Could not change that account.'));
    }
  }

  return (
    <div>
      <form
        className="mb-3 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name or email"
          className="w-64 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="">Any role</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {titleCase(r)}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          Search
        </button>
        {data && <span className="text-xs text-slate-500">{data.total} total</span>}
      </form>

      {(error || actionError) && <p className="mb-2 text-sm text-rose-600">{error ?? actionError}</p>}
      {!data && !error ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium">Email</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {data?.items.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-3 py-2">
                    <div className="font-medium text-slate-800">{row.display_name ?? '—'}</div>
                    <div className="text-xs text-slate-500">{row.email}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{titleCase(row.role)}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {row.email_verified ? 'Verified' : 'Unverified'}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        row.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                      }`}
                    >
                      {row.is_active ? 'Active' : 'Suspended'}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    {row.id === me?.id ? (
                      <span className="text-xs text-slate-400">You</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void toggle(row)}
                        className="text-xs font-medium text-blue-700 hover:underline"
                      >
                        {row.is_active ? 'Suspend' : 'Reactivate'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && data.items.length === 0 && (
            <p className="p-4 text-sm text-slate-500">No users match.</p>
          )}
        </div>
      )}
    </div>
  );
}
