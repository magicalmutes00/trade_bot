import { useCallback, useEffect, useState } from 'react'
import { api, type AdminUserRow } from '../api'

export default function UsersPage() {
  const [rows, setRows] = useState<AdminUserRow[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async (query: string) => {
    try {
      const page = await api.users(query)
      setRows(page.items)
      setTotal(page.total)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [])

  useEffect(() => { void load('') }, [load])

  async function patch(user: AdminUserRow, change: { is_active?: boolean; role?: string }) {
    setBusyId(user.id)
    try {
      const updated = await api.updateUser(user.id, change)
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-bof-muted">Users ({total})</h2>
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            void load(e.target.value)
          }}
          placeholder="Search email / username…"
          className="ml-auto w-64 rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm outline-none focus:border-bof-accent"
        />
      </div>

      {error && <p className="mb-3 text-xs text-bof-red">{error}</p>}

      <div className="overflow-hidden rounded-xl border border-bof-border">
        <table className="w-full text-sm">
          <thead className="bg-bof-surface text-left text-xs uppercase tracking-wide text-bof-muted">
            <tr>
              <th className="px-4 py-2.5">Email</th>
              <th className="px-4 py-2.5">Username</th>
              <th className="px-4 py-2.5">Provider</th>
              <th className="px-4 py-2.5">Role</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="border-t border-bof-border">
                <td className="px-4 py-2.5">{u.email}</td>
                <td className="px-4 py-2.5 text-bof-muted">{u.username ?? '—'}</td>
                <td className="px-4 py-2.5 text-bof-muted">{u.auth_provider}</td>
                <td className="px-4 py-2.5">
                  <span className={u.role === 'ADMIN' ? 'text-bof-accent' : ''}>{u.role}</span>
                </td>
                <td className="px-4 py-2.5">
                  <span className={u.is_active ? 'text-bof-green' : 'text-bof-red'}>
                    {u.is_active ? 'active' : 'disabled'}
                  </span>
                </td>
                <td className="space-x-2 px-4 py-2.5 text-right">
                  <button
                    disabled={busyId === u.id}
                    onClick={() => void patch(u, { is_active: !u.is_active })}
                    className="rounded border border-bof-border px-2 py-1 text-xs hover:border-bof-accent hover:text-bof-accent disabled:opacity-40"
                  >
                    {u.is_active ? 'Disable' : 'Enable'}
                  </button>
                  <button
                    disabled={busyId === u.id}
                    onClick={() => void patch(u, { role: u.role === 'ADMIN' ? 'USER' : 'ADMIN' })}
                    className="rounded border border-bof-border px-2 py-1 text-xs hover:border-bof-accent hover:text-bof-accent disabled:opacity-40"
                  >
                    {u.role === 'ADMIN' ? 'Demote' : 'Promote'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
