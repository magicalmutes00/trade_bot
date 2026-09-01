package com.bofedge.feature.instrument.chart

import com.bofedge.domain.model.Candle
import com.bofedge.domain.model.TradePattern
import java.time.OffsetDateTime
import kotlin.math.abs

/**
 * A horizontal trade-level line drawn on the native chart.
 * `tag` is the axis label ("Neckline", "Entry", "SL", "T1", ...).
 */
data class ChartLevel(val tag: String, val price: Double)

/**
 * Maps server-side strict patterns (spec §35) into chart overlays.
 *
 * Price levels come straight from the backend (neckline / entry / SL / target)
 * and are robust — they are absolute prices that exist regardless of which
 * bars are on screen. The confirm marker is placed on the real bar whose
 * timestamp matches `detectedAt` (the anchor/confirm bar), so it is never
 * guessed from pattern-window indices that don't line up with the client's
 * candle window.
 */
internal fun List<TradePattern>.toNativeLevels(): List<ChartLevel> {
    val out = mutableListOf<ChartLevel>()
    for (p in this) {
        p.necklinePrice?.takeIf { it > 0 }?.let { out += ChartLevel("Neckline", it) }
        p.entry?.toPrice().let { if (it != null) out += ChartLevel("Entry", it) }
        p.stopLoss?.toPrice().let { if (it != null) out += ChartLevel("SL", it) }
        p.target1?.toPrice().let { if (it != null) out += ChartLevel("T1", it) }
    }
    return out.distinctBy { it.tag to it.price }
}

/** JS bridge entries for the TradingView renderer: dashed price lines plus a
 *  confirm marker placed on the matching candle (same UTC day).
 *
 *  HARD RANGE GUARD: any pattern level whose price lies outside the visible
 *  candle band (with 10% margin) is dropped. This protects against stale
 *  patterns from a previous symbol/timeframe (e.g. RELIANCE Entry=3639 on a
 *  fresh AXISBANK chart priced ~1235) even if the ViewModel fails to clear
 *  `_tradePatterns` before the new payload arrives. */
internal fun List<TradePattern>.toJsMarkers(candles: List<Candle>): List<Map<String, Any>> {
    if (isEmpty() || candles.isEmpty()) return emptyList()
    val (lo, hi) = candles.aggregateRange()
    val margin = (hi - lo) * 0.10
    val inRange: (Double) -> Boolean = { p -> p >= lo - margin && p <= hi + margin }

    val out = mutableListOf<Map<String, Any>>()
    val dayBuckets = candles.mapIndexed { i, c -> c.timeMillis / DAY_MS to i }
        .groupBy { it.first }
    for (p in this) {
        p.necklinePrice?.takeIf { it > 0 }?.takeIf(inRange)?.let {
            out += mapOf(
                "kind" to "price-line", "price" to it, "title" to "Neckline",
                "color" to "#4E9CFF",
            )
        }
        p.entry?.toPrice()?.takeIf(inRange)?.let {
            out += mapOf("kind" to "price-line", "price" to it, "title" to "Entry", "color" to "#4E9CFF")
        }
        p.stopLoss?.toPrice()?.takeIf(inRange)?.let {
            out += mapOf("kind" to "price-line", "price" to it, "title" to "SL", "color" to "#EA3943")
        }
        p.target1?.toPrice()?.takeIf(inRange)?.let {
            out += mapOf("kind" to "price-line", "price" to it, "title" to "T1", "color" to "#16C784")
        }
        val confirm = p.detectedAt?.toEpochSecond()?.let { targetSec ->
            // exact-bar match first, then the last bar of the same UTC day
            candles.firstOrNull { it.timeMillis / 1000L == targetSec }?.timeMillis
                ?: dayBuckets[(targetSec * 1000L) / DAY_MS]
                ?.maxByOrNull { (_, idx) -> idx }   // latest int index = last bar
                ?.let { candles[it.second].timeMillis }
        }
        if (confirm != null) {
            out += mapOf(
                "kind" to "marker", "time" to confirm / 1000L,
                "position" to if (p.isBullish) "belowBar" else "aboveBar",
                "shape" to "circle", "color" to if (p.isBullish) "#16C784" else "#EA3943",
                "text" to p.patternDetected.take(24),
            )
        }
    }
    return out
}

/** Median-based min/max of all candle prices; uses mid-of-OHLC per bar to
 *  resist single-bar outliers skewing the band. */
private fun List<Candle>.aggregateRange(): Pair<Double, Double> {
    val mids = map { (it.high + it.low) / 2.0 }.sorted()
    val n = mids.size
    val median = mids[n / 2]
    if (median <= 0) {
        // Fallback: literal min/max
        var lo = Double.POSITIVE_INFINITY
        var hi = Double.NEGATIVE_INFINITY
        forEach { c -> if (c.low < lo) lo = c.low; if (c.high > hi) hi = c.high }
        return lo to hi
    }
    // Filter to the [0.2×median, 5×median] band — anything further is clearly
    // contaminated (different symbol / currency).
    val clean = filter { c ->
        val m = (c.high + c.low) / 2.0
        m > 0 && m >= median * 0.2 && m <= median * 5.0
    }.ifEmpty { this }
    var lo = Double.POSITIVE_INFINITY
    var hi = Double.NEGATIVE_INFINITY
    for (c in clean) { if (c.low < lo) lo = c.low; if (c.high > hi) hi = c.high }
    return lo to hi
}

private const val DAY_MS = 86_400_000L

/** Wire price strings are "139.00" or "149.20 (measured height)" — parse the
 *  leading number and ignore the annotation. Null for "N/A" / blank. */
private fun String?.toPrice(): Double? {
    val s = this ?: return null
    val num = s.takeWhile { it.isDigit() || it == '.' || it == '-' || it == '+' }
    val v = num.toDoubleOrNull() ?: return null
    return v.takeIf { it > 0 && it.isFinite() && abs(it) < 1e9 }
}

private fun String.toEpochSecond(): Long? = try {
    OffsetDateTime.parse(this).toEpochSecond()
} catch (_: Exception) {
    null
}