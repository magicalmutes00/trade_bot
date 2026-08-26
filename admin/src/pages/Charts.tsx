/** Charts — TradingView lightweight-charts over the public candles API. */

import { useEffect, useMemo, useState } from 'react'
import { api, type Candle, type CoverageRow } from '../api'
import TradingViewChart, { type ChartIndicators } from '../components/TradingViewChart'

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1D', '1W']

export default function ChartsPage() {
  const [instruments, setInstruments] = useState<CoverageRow[]>([])
  const [symbolId, setSymbolId] = useState<string>('')
  const [timeframe, setTimeframe] = useState('15m')
  const [indicators, setIndicators] = useState<ChartIndicators>({
    sma20: true, ema9: false, bb: false, rsi: false,
  })
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')

  // Load instrument list once (public endpoint).
  useEffect(() => {
    api.instruments('', 100)
      .then((page) => {
        setInstruments(page.items)
        if (page.items.length && !symbolId) setSymbolId(page.items[0].id)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load instruments'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load candles whenever symbol/timeframe changes.
  useEffect(() => {
    if (!symbolId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    api.candles(symbolId, timeframe, 500)
      .then((page) => { if (!cancelled) setCandles(page.items) })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load candles') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbolId, timeframe])

  const selected = useMemo(
    () => instruments.find((i) => i.id === symbolId),
    [instruments, symbolId],
  )
  const visibleSymbols = useMemo(
    () => instruments.filter((i) => i.symbol.toLowerCase().includes(filter.toLowerCase())),
    [instruments, filter],
  )

  function toggleIndicator(key: keyof ChartIndicators) {
    setIndicators((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-bof-muted">
          Charts
        </h2>
        {selected && (
          <span className="text-sm font-semibold text-bof-text">{selected.symbol}</span>
        )}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {/* Symbol picker */}
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="hidden"
            aria-hidden
          />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter symbols…"
            className="w-40 rounded-md border border-bof-border bg-bof-surface px-3 py-1.5 text-xs text-bof-text placeholder:text-bof-muted focus:border-bof-accent focus:outline-none"
          />
          <select
            value={symbolId}
            onChange={(e) => setSymbolId(e.target.value)}
            className="rounded-md border border-bof-border bg-bof-surface px-3 py-1.5 text-xs text-bof-text focus:border-bof-accent focus:outline-none"
          >
            {(visibleSymbols.length ? visibleSymbols : instruments).map((i) => (
              <option key={i.id} value={i.id}>{i.symbol}</option>
            ))}
          </select>

          {/* Timeframe */}
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="rounded-md border border-bof-border bg-bof-surface px-3 py-1.5 text-xs text-bof-accent focus:border-bof-accent focus:outline-none"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>{tf}</option>
            ))}
          </select>

          {/* Indicator toggles */}
          {(
            [
              ['sma20', 'SMA20'],
              ['ema9', 'EMA9'],
              ['bb', 'BB'],
              ['rsi', 'RSI'],
            ] as [keyof ChartIndicators, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => toggleIndicator(key)}
              className={`rounded-md border px-3 py-1.5 text-xs transition ${
                indicators[key]
                  ? 'border-bof-accent bg-bof-accent/10 text-bof-accent'
                  : 'border-bof-border text-bof-muted hover:text-bof-text'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="mb-3 rounded-md border border-bof-red/40 bg-bof-red/10 px-3 py-2 text-xs text-bof-red">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-xl border border-bof-border bg-[#0B0F14]">
        {loading && !candles.length ? (
          <div className="flex h-[460px] items-center justify-center text-sm text-bof-muted">
            Loading candles…
          </div>
        ) : candles.length ? (
          <TradingViewChart candles={candles} indicators={indicators} />
        ) : (
          <div className="flex h-[460px] items-center justify-center text-sm text-bof-muted">
            {selected ? `No ${timeframe} candles for ${selected.symbol} yet.` : 'Pick a symbol.'}
          </div>
        )}
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-bof-muted">
        Data: backend candle store ({candles.length} bars · {timeframe}) — scroll to zoom,
        drag to pan, hover for OHLCV. RSI renders in its own pane below.
      </p>
    </section>
  )
}
