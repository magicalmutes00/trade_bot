/**
 * TradingView lightweight-charts wrapper — candlestick + volume + overlays.
 *
 * Mirrors the Android KiteStyleChart feature set:
 *   candles · volume histogram · SMA20 · EMA9 · Bollinger(20,2) · RSI(14) pane
 *   crosshair legend with OHLCV and % change vs previous close.
 */

import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Candle } from '../api'

const UP = '#16C784'
const DOWN = '#EA3943'
const GRID = '#1A2230'
const TEXT = '#8A97A8'
const BG = '#0B0F14'
const ACCENT = '#4E9CFF'
const SMA20_COLOR = '#FF9800'
const EMA9_COLOR = '#E040FB'
const BB_COLOR = 'rgba(78,156,255,0.55)'

export interface ChartIndicators {
  sma20: boolean
  ema9: boolean
  bb: boolean
  rsi: boolean
}

interface LegendState {
  o: number; h: number; l: number; c: number; v: number; pct: number | null
}

// ------------------------------------------------------------ indicator math

function sma(values: (number | null)[], period: number): (number | null)[] {
  const out: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (v != null) sum += v
    if (i >= period && values[i - period] != null) sum -= values[i - period] as number
    out.push(i >= period - 1 ? sum / period : null)
  }
  return out
}

function ema(values: (number | null)[], period: number): (number | null)[] {
  const out: (number | null)[] = []
  if (!values.length) return out
  const k = 2 / (period + 1)
  let prev: number | null = null
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (v == null) { out.push(null); continue }
    if (prev == null) {
      if (i < period - 1) { out.push(null); continue }
      let s = 0
      for (let j = i - period + 1; j <= i; j++) s += values[j] as number
      prev = s / period
    } else {
      prev = v * k + prev * (1 - k)
    }
    out.push(prev)
  }
  return out
}

function bollinger(values: (number | null)[], period = 20, mult = 2) {
  const upper: (number | null)[] = []
  const lower: (number | null)[] = []
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1 || values[i] == null) { upper.push(null); lower.push(null); continue }
    const win = values.slice(i - period + 1, i + 1).map((v) => v as number)
    const mean = win.reduce((a, b) => a + b, 0) / period
    const std = Math.sqrt(win.reduce((a, b) => a + (b - mean) ** 2, 0) / period)
    upper.push(mean + mult * std)
    lower.push(mean - mult * std)
  }
  return { upper, lower }
}

function rsi(closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = closes.map(() => null)
  if (closes.length <= period) return out
  let gain = 0, loss = 0
  for (let i = 1; i <= period; i++) {
    const chg = closes[i] - closes[i - 1]
    if (chg > 0) gain += chg; else loss -= chg
  }
  gain /= period; loss /= period
  const val = (g: number, l: number) => (l === 0 && g === 0 ? 50 : l === 0 ? 100 : 100 - 100 / (1 + g / l))
  out[period] = val(gain, loss)
  for (let i = period + 1; i < closes.length; i++) {
    const chg = closes[i] - closes[i - 1]
    gain = (gain * (period - 1) + Math.max(chg, 0)) / period
    loss = (loss * (period - 1) + Math.max(-chg, 0)) / period
    out[i] = val(gain, loss)
  }
  return out
}

function toLineData(
  times: UTCTimestamp[],
  values: (number | null)[],
): { time: UTCTimestamp; value: number }[] {
  const out: { time: UTCTimestamp; value: number }[] = []
  for (let i = 0; i < times.length; i++) {
    const v = values[i]
    if (v != null) out.push({ time: times[i], value: v })
  }
  return out
}

// ---------------------------------------------------------------- component

export default function TradingViewChart(props: {
  candles: Candle[]
  indicators: ChartIndicators
}) {  const { candles, indicators } = props
  const containerRef = useRef<HTMLDivElement>(null)
  const legendRef = useRef<HTMLDivElement>(null)

  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const smaRef = useRef<ISeriesApi<'Line'> | null>(null)
  const emaRef = useRef<ISeriesApi<'Line'> | null>(null)
  const bbURef = useRef<ISeriesApi<'Line'> | null>(null)
  const bbLRef = useRef<ISeriesApi<'Line'> | null>(null)
  const rsiRef = useRef<ISeriesApi<'Line'> | null>(null)
  const lastBarRef = useRef<LegendState | null>(null)

  // ---- create once
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { color: BG },
        textColor: TEXT,
        fontSize: 11,
        panes: { separatorColor: GRID, separatorHoverColor: ACCENT },
      },
      grid: {
        vertLines: { color: GRID },
        horzLines: { color: GRID },
      },
      crosshair: {
        vertLine: { color: ACCENT, labelBackgroundColor: ACCENT },
        horzLine: { color: ACCENT, labelBackgroundColor: ACCENT },
      },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: GRID },
      rightPriceScale: { borderColor: GRID },
    })
    chartRef.current = chart

    candleRef.current = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, wickUpColor: UP, wickDownColor: DOWN,
      borderVisible: false,
    })

    volRef.current = chart.addSeries(HistogramSeries, {
      priceScaleId: '',
      priceFormat: { type: 'volume' },
      lastValueVisible: false,
      priceLineVisible: false,
    })
    volRef.current.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })

    smaRef.current = chart.addSeries(LineSeries, {
      color: SMA20_COLOR, lineWidth: 2, title: 'SMA20', visible: false,
    })
    emaRef.current = chart.addSeries(LineSeries, {
      color: EMA9_COLOR, lineWidth: 2, title: 'EMA9', visible: false,
    })
    bbURef.current = chart.addSeries(LineSeries, {
      color: BB_COLOR, lineWidth: 1, title: 'BB↑', visible: false,
      lineStyle: 2,
    })
    bbLRef.current = chart.addSeries(LineSeries, {
      color: BB_COLOR, lineWidth: 1, title: 'BB↓', visible: false,
      lineStyle: 2,
    })
    // RSI series is created lazily in the data effect so its pane only
    // exists while RSI is enabled (v5 removes empty panes automatically).

    chart.subscribeCrosshairMove((param) => {
      const bar = param.seriesData.get(candleRef.current!) as
        | { open: number; high: number; low: number; close: number }
        | undefined
      const vol = param.seriesData.get(volRef.current!) as { value: number } | undefined
      if (bar && legendRef.current) {
        const base = lastBarRef.current?.pct ?? null
        renderLegend(legendRef.current, bar.open, bar.high, bar.low, bar.close,
          vol?.value ?? 0, base, true)
      } else if (lastBarRef.current && legendRef.current) {
        const b = lastBarRef.current
        renderLegend(legendRef.current, b.o, b.h, b.l, b.c, b.v, b.pct, false)
      }
    })

    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [])

  // ---- feed data + toggle indicator visibility
  useEffect(() => {
    const chart = chartRef.current
    const candleS = candleRef.current
    if (!chart || !candleS || !candles.length) return

    // Backend returns newest-first — flip and de-duplicate by timestamp.
    const sorted = [...candles].reverse()
    const seen = new Set<number>()
    const bars: {
      time: UTCTimestamp; open: number; high: number; low: number; close: number
    }[] = []
    const vols: { time: UTCTimestamp; value: number; color: string }[] = []

    for (const c of sorted) {
      const t = Math.floor(new Date(c.ts).getTime() / 1000) as UTCTimestamp
      if (seen.has(t)) continue
      seen.add(t)
      bars.push({ time: t, open: c.open, high: c.high, low: c.low, close: c.close })
      vols.push({
        time: t, value: c.volume,
        color: c.close >= c.open ? `${UP}55` : `${DOWN}55`,
      })
    }
    if (!bars.length) return

    candleS.setData(bars)
    volRef.current?.setData(vols)

    const times = bars.map((b) => b.time)
    const closes = bars.map((b) => b.close)
    const closeVals: (number | null)[] = closes.map((v) => v)

    smaRef.current?.setData(toLineData(times, sma(closeVals, 20)))
    emaRef.current?.setData(toLineData(times, ema(closeVals, 9)))
    const bb = bollinger(closeVals, 20, 2)
    bbURef.current?.setData(toLineData(times, bb.upper))
    bbLRef.current?.setData(toLineData(times, bb.lower))
    rsiRef.current?.setData(toLineData(times, rsi(closes, 14)))

    smaRef.current?.applyOptions({ visible: indicators.sma20 })
    emaRef.current?.applyOptions({ visible: indicators.ema9 })
    bbURef.current?.applyOptions({ visible: indicators.bb })
    bbLRef.current?.applyOptions({ visible: indicators.bb })

    // RSI pane lifecycle: create/remove the series so v5 adds/drops its pane.
    if (indicators.rsi) {
      if (!rsiRef.current && chart) {
        const s = chart.addSeries(LineSeries, {
          color: ACCENT, lineWidth: 2, title: 'RSI14',
        }, 1)
        s.createPriceLine({ price: 70, color: TEXT, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' })
        s.createPriceLine({ price: 30, color: TEXT, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' })
        rsiRef.current = s
      }
      rsiRef.current?.setData(toLineData(times, rsi(closes, 14)))
    } else if (rsiRef.current && chart) {
      chart.removeSeries(rsiRef.current)
      rsiRef.current = null
    }

    const last = bars[bars.length - 1]
    const prev = bars.length > 1 ? bars[bars.length - 2].close : last.open
    const pct = prev ? ((last.close - prev) / prev) * 100 : null
    lastBarRef.current = {
      o: last.open, h: last.high, l: last.low, c: last.close,
      v: vols[vols.length - 1]?.value ?? 0, pct,
    }
    if (legendRef.current) {
      renderLegend(legendRef.current, last.open, last.high, last.low, last.close,
        lastBarRef.current.v, pct, false)
    }

    chart.timeScale().fitContent()
  }, [candles, indicators])

  return (
    <div className="relative">
      <div
        ref={legendRef}
        className="pointer-events-none absolute left-3 top-2 z-10 rounded-md bg-[#121821E6] px-2.5 py-1.5 text-[11px] leading-4 font-mono"
      />
      <div ref={containerRef} className="h-[460px] w-full" />
    </div>
  )
}

function renderLegend(
  el: HTMLDivElement,
  o: number, h: number, l: number, c: number, v: number,
  pct: number | null, hovering: boolean,
) {
  const up = c >= o
  const color = up ? UP : DOWN
  const pctStr = pct == null ? '' : ` ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
  const tag = hovering ? '· hover' : ''
  el.innerHTML =
    `<div style="color:${color}">O ${o.toFixed(2)} H ${h.toFixed(2)} L ${l.toFixed(2)} C ${c.toFixed(2)}${pctStr}</div>` +
    `<div style="color:${color}CC">V ${v.toLocaleString('en-IN')}${tag}</div>`
}
