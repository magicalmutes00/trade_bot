import { useCallback, useEffect, useState } from 'react'
import { api, type SignalRow } from '../api'

const STATUSES = ['', 'DETECTING', 'CONFIRMED', 'INVALIDATED', 'CLOSED']
const DIRECTIONS = ['', 'BULLISH', 'BEARISH']

function badgeColor(status: string): string {
  if (status === 'CONFIRMED') return 'text-bof-green'
  if (status === 'INVALIDATED') return 'text-bof-red'
  return 'text-bof-muted'
}

export default function SignalsPage() {
  const [rows, setRows] = useState<SignalRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [direction, setDirection] = useState('')
  const [error, setError] = useState<string | null>(null)
  const limit = 50

  const load = useCallback(async () => {
    try {
      const page = await api.signals({ status, direction }, limit, offset)
      setRows(page.items)
      setTotal(page.total)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [status, direction, offset])

  useEffect(() => { void load() }, [load])

  function changeFilter(setter: (v: string) => void) {
    return (v: string) => { setter(v); setOffset(0) }
  }

  return (
    <section>
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-bof-muted">
          Signals ({total})
        </h2>
        <select
          value={status}
          onChange={(e) => changeFilter(setStatus)(e.target.value)}
          className="ml-auto rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s || 'All statuses'}</option>)}
        </select>
        <select
          value={direction}
          onChange={(e) => changeFilter(setDirection)(e.target.value)}
          className="rounded-md border border-bof-border bg-bof-black px-3 py-1.5 text-sm"
        >
          {DIRECTIONS.map((d) => <option key={d} value={d}>{d || 'All directions'}</option>)}
        </select>
      </div>

      {error && <p className="mb-3 text-xs text-bof-red">{error}</p>}

      <div className="overflow-hidden rounded-xl border border-bof-border">
        <table className="w-full text-sm">
          <thead className="bg-bof-surface text-left text-xs uppercase tracking-wide text-bof-muted">
            <tr>
              <th className="px-4 py-2.5">Symbol</th>
              <th className="px-4 py-2.5">Direction</th>
              <th className="px-4 py-2.5">Strength</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">TF</th>
              <th className="px-4 py-2.5">Confidence</th>
              <th className="px-4 py-2.5">Detected</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-bof-border">
                <td className="px-4 py-2.5 font-medium">{r.symbol}</td>
                <td className={`px-4 py-2.5 ${r.direction === 'BULLISH' ? 'text-bof-green' : 'text-bof-red'}`}>
                  {r.direction}
                </td>
                <td className="px-4 py-2.5">{r.strength.replace('_', ' ')}</td>
                <td className={`px-4 py-2.5 ${badgeColor(r.status)}`}>{r.status}</td>
                <td className="px-4 py-2.5 text-bof-muted">{r.timeframe}</td>
                <td className="px-4 py-2.5 font-mono">{(r.confidence * 100).toFixed(0)}%</td>
                <td className="px-4 py-2.5 font-mono text-xs">{new Date(r.detected_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex gap-2">
        <button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - limit))}
          className="rounded-md border border-bof-border px-3 py-1.5 text-xs text-bof-muted disabled:opacity-40"
        >
          ← Prev
        </button>
        <button
          disabled={offset + limit >= total}
          onClick={() => setOffset(offset + limit)}
          className="rounded-md border border-bof-border px-3 py-1.5 text-xs text-bof-muted disabled:opacity-40"
        >
          Next →
        </button>
        <span className="ml-auto self-center text-xs text-bof-muted">
          showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
        </span>
      </div>
    </section>
  )
}
