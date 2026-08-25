import { useCallback, useEffect, useState } from 'react'
import { api, type AdminHealthInfo } from '../api'

export default function HealthPage() {
  const [info, setInfo] = useState<AdminHealthInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setInfo(await api.health())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), 20_000)
    return () => clearInterval(id)
  }, [load])

  if (error) return <p className="text-sm text-bof-red">{error}</p>
  if (!info) return <p className="text-sm text-bof-muted">Loading…</p>

  const rows: [string, string][] = [
    ['Overall status', info.status],
    ['Database latency', info.database_latency_ms !== null ? `${info.database_latency_ms} ms` : '—'],
    ['WebSocket connections', String(info.ws_connections)],
    ['Data provider', info.provider],
    ['Live demo loop', info.live_loop_enabled ? 'enabled' : 'disabled'],
    ['API version', info.version],
  ]

  return (
    <section className="max-w-xl">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-bof-muted">
        System health
      </h2>
      <div className="rounded-xl border border-bof-border bg-bof-surface">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between border-b border-bof-border px-5 py-3 last:border-b-0">
            <span className="text-xs uppercase tracking-wide text-bof-muted">{k}</span>
            <span className="font-mono text-sm">{v}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
