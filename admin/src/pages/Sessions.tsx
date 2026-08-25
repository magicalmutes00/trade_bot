import { useCallback, useEffect, useState } from 'react'
import { api, type SessionRow } from '../api'

const MARKETS = ['NSE', 'BSE', 'MCX', 'CDS', 'CRYPTO']
const STATUSES = ['OPEN', 'PRE_OPEN', 'CLOSED', 'HALF_DAY', 'HOLIDAY']

export default function SessionsPage() {
  const [rows, setRows] = useState<SessionRow[]>([])
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [market, setMarket] = useState('NSE')
  const [status, setStatus] = useState('HOLIDAY')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await api.sessions())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try {
      await api.upsertSession({ session_date: date, market, status, note: note || undefined })
      setNote('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  return (
    <section>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-bof-muted">
        Market sessions
      </h2>

      <form onSubmit={(e) => void submit(e)}
            className="mb-6 flex flex-wrap items-end gap-3 rounded-xl border border-bof-border bg-bof-surface p-4">
        <label className="text-xs text-bof-muted">
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                 className="mt-1 block rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm" />
        </label>
        <label className="text-xs text-bof-muted">
          Market
          <select value={market} onChange={(e) => setMarket(e.target.value)}
                  className="mt-1 block rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm">
            {MARKETS.map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        <label className="text-xs text-bof-muted">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}
                  className="mt-1 block rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm">
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex-1 text-xs text-bof-muted">
          Note (optional)
          <input value={note} onChange={(e) => setNote(e.target.value)}
                 placeholder="e.g. Gandhi Jayanti"
                 className="mt-1 block w-full rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm" />
        </label>
        <button type="submit"
                className="rounded-md bg-bof-accent px-4 py-2 text-sm font-medium text-bof-black hover:opacity-90">
          Upsert entry
        </button>
      </form>

      {error && <p className="mb-3 text-xs text-bof-red">{error}</p>}

      <div className="overflow-hidden rounded-xl border border-bof-border">
        <table className="w-full text-sm">
          <thead className="bg-bof-surface text-left text-xs uppercase tracking-wide text-bof-muted">
            <tr>
              <th className="px-4 py-2.5">Date</th>
              <th className="px-4 py-2.5">Market</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">Note</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-bof-border">
                <td className="px-4 py-2.5 font-mono">{r.session_date}</td>
                <td className="px-4 py-2.5">{r.market}</td>
                <td className={`px-4 py-2.5 ${
                  r.status === 'HOLIDAY' ? 'text-bof-red'
                    : r.status === 'HALF_DAY' ? 'text-yellow-500' : ''}`}>
                  {r.status}
                </td>
                <td className="px-4 py-2.5 text-bof-muted">{r.note ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
