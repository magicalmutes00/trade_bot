import { useCallback, useEffect, useState } from 'react'
import { api, type EventRow } from '../api'

const LEVELS = ['', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

function levelColor(level: string): string {
  switch (level) {
    case 'ERROR': return 'text-bof-red'
    case 'CRITICAL': return 'text-bof-red font-semibold'
    case 'WARNING': return 'text-yellow-500'
    default: return 'text-bof-text'
  }
}

export default function LogsPage() {
  const [rows, setRows] = useState<EventRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [level, setLevel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const limit = 100

  const load = useCallback(async () => {
    try {
      const page = await api.events(level, limit, offset)
      setRows(page.items)
      setTotal(page.total)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [level, offset])

  useEffect(() => { void load() }, [load])

  return (
    <section>
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-bof-muted">
          System events ({total})
        </h2>
        <select value={level} onChange={(e) => { setLevel(e.target.value); setOffset(0) }}
                className="ml-auto rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm">
          {LEVELS.map((l) => <option key={l} value={l}>{l || 'All levels'}</option>)}
        </select>
      </div>

      {error && <p className="mb-3 text-xs text-bof-red">{error}</p>}

      {rows.length === 0 ? (
        <p className="rounded-lg bg-bof-surface px-4 py-6 text-center text-sm text-bof-muted">
          No events recorded yet. Pipeline failures and operational notices will
          appear here as they happen.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-bof-border">
          <table className="w-full text-sm">
            <thead className="bg-bof-surface text-left text-xs uppercase tracking-wide text-bof-muted">
              <tr>
                <th className="px-4 py-2.5">Time</th>
                <th className="px-4 py-2.5">Level</th>
                <th className="px-4 py-2.5">Source</th>
                <th className="px-4 py-2.5">Message</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-bof-border">
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className={`px-4 py-2.5 ${levelColor(r.level)}`}>{r.level}</td>
                  <td className="px-4 py-2.5 text-bof-muted">{r.source}</td>
                  <td className="px-4 py-2.5">{r.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex gap-2">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}
                className="rounded-md border border-bof-border px-3 py-1.5 text-xs text-bof-muted disabled:opacity-40">
          ← Prev
        </button>
        <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}
                className="rounded-md border border-bof-border px-3 py-1.5 text-xs text-bof-muted disabled:opacity-40">
          Next →
        </button>
      </div>
    </section>
  )
}
