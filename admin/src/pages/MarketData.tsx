import { useCallback, useEffect, useState } from 'react'
import { api, type CoverageRow } from '../api'

export default function MarketDataPage() {
  const [rows, setRows] = useState<CoverageRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const limit = 100

  const load = useCallback(async () => {
    try {
      const page = await api.coverage(limit, offset)
      setRows(page.items)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [limit, offset])

  useEffect(() => { void load() }, [load])

  return (
    <section>
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-bof-muted">
          Market data pipeline status
        </h2>
        <button
          onClick={() => void load()}
          className="ml-auto rounded-md border border-bof-border px-3 py-1.5 text-xs text-bof-muted hover:border-bof-accent hover:text-bof-accent"
        >
          Refresh
        </button>
      </div>

      {error && <p className="mb-3 text-xs text-bof-red">{error}</p>}

      <p className="mb-3 text-xs leading-relaxed text-bof-muted">
        Healthy rows show a growing M15 candle count and a quote timestamp within
        the last few minutes of the demo loop running.
      </p>

      <div className="overflow-hidden rounded-xl border border-bof-border">
        <table className="w-full text-sm">
          <thead className="bg-bof-surface text-left text-xs uppercase tracking-wide text-bof-muted">
            <tr>
              <th className="px-4 py-2.5">Symbol</th>
              <th className="px-4 py-2.5">M15 candles</th>
              <th className="px-4 py-2.5">Last candle</th>
              <th className="px-4 py-2.5">Quote age</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const ageMin = r.quote_updated_at
                ? Math.round((Date.now() - new Date(r.quote_updated_at).getTime()) / 60000)
                : null
              return (
                <tr key={r.symbol} className="border-t border-bof-border">
                  <td className="px-4 py-2.5 font-medium">{r.symbol}</td>
                  <td className="px-4 py-2.5 font-mono">{r.m15_candles}</td>
                  <td className="px-4 py-2.5 font-mono text-xs">{fmt(r.last_m15_ts)}</td>
                  <td className={`px-4 py-2.5 font-mono text-xs ${
                    ageMin === null ? 'text-bof-muted'
                      : ageMin < 10 ? 'text-bof-green' : 'text-yellow-500'}`}>
                    {ageMin === null ? '—' : `${ageMin} min ago`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex gap-2">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}
                className="rounded-md border border-bof-border px-3 py-1.5 text-xs text-bof-muted disabled:opacity-40">
          ← Prev
        </button>
        <button disabled={rows.length < limit} onClick={() => setOffset(offset + limit)}
                className="rounded-md border border-bof-border px-3 py-1.5 text-xs text-bof-muted disabled:opacity-40">
          Next →
        </button>
      </div>
    </section>
  )
}

function fmt(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}
