import { useCallback, useEffect, useState } from 'react'
import { api, type AdminStats } from '../api'

function StatCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-bof-border bg-bof-surface p-4">
      <div className="text-xs uppercase tracking-wide text-bof-muted">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${accent ?? 'text-bof-text'}`}>{value}</div>
    </div>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setStats(await api.stats())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), 30_000)
    return () => clearInterval(id)
  }, [load])

  if (error) {
    return <p className="rounded-lg bg-bof-red/10 px-4 py-3 text-sm text-bof-red">{error}</p>
  }
  if (!stats) return <p className="text-sm text-bof-muted">Loading…</p>

  return (
    <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <StatCard label="Active users" value={String(stats.active_users)} />
      <StatCard label="Total users" value={String(stats.total_users)} />
      <StatCard label="Signals today" value={String(stats.signals_today)} accent="text-bof-accent" />
      <StatCard label="Total signals" value={String(stats.total_signals)} />
      <StatCard label="Confirmed" value={String(stats.confirmed_signals)} accent="text-bof-green" />
      <StatCard label="Invalidated" value={String(stats.invalidated_signals)} accent="text-bof-red" />
      <StatCard label="Instruments" value={String(stats.active_instruments)} />
      <StatCard
        label="Database"
        value={stats.database}
        accent={stats.database === 'up' ? 'text-bof-green' : 'text-bof-red'}
      />
      <StatCard label="WS connections" value={String(stats.ws_connections)} />
      <StatCard label="Provider" value={stats.provider} />
      <StatCard label="Environment" value={stats.environment} />
    </section>
  )
}
