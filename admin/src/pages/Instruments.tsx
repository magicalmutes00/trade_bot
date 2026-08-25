import { useCallback, useEffect, useState } from 'react'
import { api, type CoverageRow } from '../api'

function fmtTs(ts: string | null): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

export default function InstrumentsPage() {
  const [rows, setRows] = useState<CoverageRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const page = await api.coverage()
      setRows(page.items)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  async function toggleActive(row: CoverageRow) {
    setBusyId(row.id)
    try {
      await api.updateInstrument(row.id, { is_active: !row.is_active })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-bof-muted">
        Instruments & candle coverage ({rows.length})
      </h2>
      {error && <p className="mb-3 text-xs text-bof-red">{error}</p>}

      <div className="overflow-hidden rounded-xl border border-bof-border">
        <table className="w-full text-sm">
          <thead className="bg-bof-surface text-left text-xs uppercase tracking-wide text-bof-muted">
            <tr>
              <th className="px-4 py-2.5">Symbol</th>
              <th className="px-4 py-2.5">Exchange</th>
              <th className="px-4 py-2.5">M15 candles</th>
              <th className="px-4 py-2.5">Last candle</th>
              <th className="px-4 py-2.5">Quote updated</th>
              <th className="px-4 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={`border-t border-bof-border ${r.is_active ? '' : 'opacity-50'}`}>
                <td className="px-4 py-2.5 font-medium">{r.symbol}</td>
                <td className="px-4 py-2.5 text-bof-muted">{r.exchange}</td>
                <td className="px-4 py-2.5 font-mono">{r.m15_candles}</td>
                <td className="px-4 py-2.5 font-mono text-xs">{fmtTs(r.last_m15_ts)}</td>
                <td className="px-4 py-2.5 font-mono text-xs">{fmtTs(r.quote_updated_at)}</td>
                <td className="px-4 py-2.5 text-right">
                  <button
                    disabled={busyId === r.id}
                    onClick={() => void toggleActive(r)}
                    className="rounded border border-bof-border px-2 py-1 text-xs hover:border-bof-accent hover:text-bof-accent disabled:opacity-40"
                  >
                    {r.is_active ? 'Deactivate' : 'Activate'}
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
