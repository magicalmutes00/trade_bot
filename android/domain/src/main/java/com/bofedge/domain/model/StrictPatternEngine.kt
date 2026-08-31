package com.bofedge.domain.model

import kotlin.math.abs
import kotlin.math.round

/**
 * Pure Kotlin port of the backend strict pattern engine
 * (`backend/app/engine/{patterns,swings,market_structure}.py`) — the source of
 * truth for TRADEBOT's strict rules. Produces results identical to
 * `GET /instruments/{id}/patterns` so charts/UI can compute locally.
 *
 * Pipeline mirrors the backend 1:1:
 *   1. `confirmPivots`      — fractal pivot detection (strict-left, >= right)
 *   2. `mergeSameSide`      — collapse same-side runs to most extreme
 *   3. split into high/low swings
 *   4. `detectDoubleTop` / `detectDoubleBottom` / `detectPatterns`
 *
 * Implemented ONLY for the specified patterns (Double Top §8, Double Bottom §9).
 * Do NOT apply textbook pattern definitions that aren't in the engine spec here.
 */

/** Lifecycle status of a strict pattern (spec §4). */
enum class StrictPatternStatus { FORMING, FULLY_FORMED, INVALIDATED }

/** A single pattern hit: geometry + trade plan + explicit invalidation. */
data class StrictPatternHit(
    val name: String,                        // "DOUBLE_TOP" | "DOUBLE_BOTTOM"
    val direction: PatternDirection,
    val status: StrictPatternStatus,
    val confirmIndex: Int?,                  // candle index where the pattern fired (null while FORMING)
    val necklinePrice: Double,               // breakout level (entry = neckline after breakout)
    val entry: Double,                       // price where the trade triggers
    val stopLoss: Double?,                   // structural level
    val targets: List<Double>,               // measured-move targets per spec
    val invalidation: String,                // exact condition that invalidates (§33)
    val peakPrice: Double,                   // avg of the two tops (top) / bottoms (bottom)
    val swingIndices: Triple<Int, Int, Int>, // (point1_idx, valley/peak_idx, point2_idx) candle indices
    val confidence: Double,                  // 0.0-1.0 rule-satisfaction score
    val notes: String = "",                  // rule trace / additional notes
)

object StrictPatternEngine {

    /** Every threshold mirrors `backend/app/engine/config.py` PatternConfig. */
    data class Cfg(
        val doubleSlippage: Double = 0.0032,
        val doubleMaxDays: Double = 274.0,
        val doubleConfirmBars: Int = 1,
        val doubleMinBarsBetween: Int = 3,
        val hsShoulderTolerance: Double = 0.03,
        val hsMinBarsBetween: Int = 10,
        val hsConfirmBars: Int = 1,
        val triangleMinTouches: Int = 3,
        val triangleMaxSlopeDivergence: Double = 0.25,
        val triangleMinBars: Int = 15,
        val channelConfirmBars: Int = 2,
        val harmonicTolerance: Double = 0.05,
        val harmonicTargets: List<Double> = listOf(0.618, 1.0, 1.414),
        val fibLastSwingBars: Int = 30,
    )

    enum class Side { UP, DOWN }

    /** A fractal pivot (mirrors backend `Pivot`). `timeMillis` is UTC epoch ms. */
    data class Pivot(val timeMillis: Long, val index: Int, val price: Double, val side: Side)

    /** A swing point in the alternating high/low sequence (mirrors backend `Swing`). */
    data class Swing(val timeMillis: Long, val index: Int, val price: Double, val side: Side)

    /** Alternating swing highs/lows + derived trend (mirrors `SwingStructure`). */
    data class SwingStructure(val swings: List<Swing>, val trend: PatternDirection, val highs: List<Swing>, val lows: List<Swing>)

    // ── entry point ──────────────────────────────────────────────────────────

    /** Run both detectors and return hits (newest first). */
    fun detect(candles: List<Candle>, left: Int = 3, right: Int = 3, cfg: Cfg = Cfg()): List<StrictPatternHit> {
        val structure = analyse(candles, left = left, right = right)
        return detectPatterns(structure, candles, cfg)
    }

    /** Convenience wrapper: swing sequence + trend in one call (mirrors `analyse`). */
    fun analyse(
        candles: List<Candle>,
        left: Int = 3,
        right: Int = 3,
    ): SwingStructure {
        val mergedP = mergeSameSide(confirmPivots(candles, left = left, right = right))
        val merged = mergedP.map { Swing(it.timeMillis, it.index, it.price, it.side) }
        val highs = merged.filter { it.side == Side.UP }
        val lows = merged.filter { it.side == Side.DOWN }
        return SwingStructure(
            swings = merged,
            trend = trendFromSwings(highs, lows),
            highs = highs,
            lows = lows,
        )
    }

    /**
     * Fractal pivots (mirrors `confirm_pivots`): high[i] strictly greater than
     * every high to its left within the window and >= every high to its right
     * (ties resolve to the leftmost bar). Swing low is the mirror image.
     */
    fun confirmPivots(candles: List<Candle>, left: Int = 3, right: Int = 3): List<Pivot> {
        val out = mutableListOf<Pivot>()
        val n = candles.size
        for (i in left until n - right) {
            val c = candles[i]
            val leftBlock = candles.subList(i - left, i)
            val rightBlock = candles.subList(i + 1, i + right + 1)

            if (leftBlock.all { c.high > it.high } && rightBlock.all { c.high >= it.high }) {
                out += Pivot(c.timeMillis, i, c.high, Side.UP)
            }
            if (leftBlock.all { c.low < it.low } && rightBlock.all { c.low <= it.low }) {
                out += Pivot(c.timeMillis, i, c.low, Side.DOWN)
            }
        }
        return out.sortedBy { it.index }
    }

    // ── detectors ────────────────────────────────────────────────────────────

    /** Traditional Double Top (spec §8). Mirrors `detect_double_top`. */
    fun detectDoubleTop(structure: SwingStructure, candles: List<Candle>, cfg: Cfg = Cfg()): List<StrictPatternHit> {
        val highs = structure.highs
        val lows = structure.lows
        if (highs.size < 2) return emptyList()

        val hits = mutableListOf<StrictPatternHit>()
        for (i in 0 until highs.size - 1) {
            val peak1 = highs[i]
            val peak2 = highs[i + 1]

            // 3. valley strictly between the two tops
            val valley = between(lows, peak1.index, peak2.index) ?: continue

            // 1. slippage ≤ 0.32%
            val avgPeak = (peak1.price + peak2.price) / 2
            if (pctDiff(peak1.price, peak2.price) > cfg.doubleSlippage) continue

            // 2. time between tops < 9 months
            if (spanDays(peak1.timeMillis, peak2.timeMillis) >= cfg.doubleMaxDays) continue

            // 4. confirmation: one CLOSE beyond the neckline
            val neckline = valley.price
            val confirmIdx = findCloseBreak(
                candles, start = peak2.index + 1, level = neckline,
                direction = "below", consecutive = cfg.doubleConfirmBars,
            )

            val higherTop = maxOf(peak1.price, peak2.price)
            val upperClose = anyCloseAbove(candles, start = peak2.index + 1, level = higherTop)

            val status = when {
                confirmIdx != null -> StrictPatternStatus.FULLY_FORMED
                upperClose -> StrictPatternStatus.INVALIDATED
                else -> StrictPatternStatus.FORMING
            }

            // Trade plan (spec §8): entry = neckline breakout, target = measured height
            val height = avgPeak - neckline
            val target1 = neckline - height
            val entry = neckline
            val stop = higherTop // structural: closing above the higher top invalidates

            val conf = confidence(
                slippageRatio = pctDiff(peak1.price, peak2.price) / cfg.doubleSlippage,
                depthRatio = if (avgPeak != 0.0) (height / avgPeak) / 0.05 else 1.0,
                status = status,
            )

            hits += StrictPatternHit(
                name = "DOUBLE_TOP",
                direction = PatternDirection.BEARISH,
                status = status,
                confirmIndex = confirmIdx,
                necklinePrice = neckline,
                entry = entry,
                stopLoss = stop,
                targets = listOf(round4(target1)),
                invalidation = buildString {
                    append("A candle CLOSES above the higher top ")
                    append(fmt2(higherTop))
                    append(" (spec §8: structural peak breakout)")
                },
                peakPrice = avgPeak,
                swingIndices = Triple(peak1.index, valley.index, peak2.index),
                confidence = conf,
                notes = buildString {
                    append("time_gap_days=").append(spanDays(peak1.timeMillis, peak2.timeMillis).toLong())
                    append(", slippage=").append(fmt4pct(pctDiff(peak1.price, peak2.price)))
                    append(", target=measured_height (").append(fmt2(height)).append(')')
                },
            )
        }
        return hits
    }

    /** Traditional Double Bottom (spec §9) — mirror of Double Top. */
    fun detectDoubleBottom(structure: SwingStructure, candles: List<Candle>, cfg: Cfg = Cfg()): List<StrictPatternHit> {
        val lows = structure.lows
        val highs = structure.highs
        if (lows.size < 2) return emptyList()

        val hits = mutableListOf<StrictPatternHit>()
        for (i in 0 until lows.size - 1) {
            val valley1 = lows[i]
            val valley2 = lows[i + 1]

            val peak = between(highs, valley1.index, valley2.index) ?: continue

            val avgValley = (valley1.price + valley2.price) / 2
            if (pctDiff(valley1.price, valley2.price) > cfg.doubleSlippage) continue

            if (spanDays(valley1.timeMillis, valley2.timeMillis) >= cfg.doubleMaxDays) continue

            val neckline = peak.price
            val confirmIdx = findCloseBreak(
                candles, start = valley2.index + 1, level = neckline,
                direction = "above", consecutive = cfg.doubleConfirmBars,
            )

            val lowerBottom = minOf(valley1.price, valley2.price)
            val lowerClose = anyCloseBelow(candles, start = valley2.index + 1, level = lowerBottom)

            val status = when {
                confirmIdx != null -> StrictPatternStatus.FULLY_FORMED
                lowerClose -> StrictPatternStatus.INVALIDATED
                else -> StrictPatternStatus.FORMING
            }

            val height = neckline - avgValley
            val target1 = neckline + height
            val entry = neckline
            val stop = lowerBottom

            val conf = confidence(
                slippageRatio = pctDiff(valley1.price, valley2.price) / cfg.doubleSlippage,
                depthRatio = if (avgValley != 0.0) (height / avgValley) / 0.05 else 1.0,
                status = status,
            )

            hits += StrictPatternHit(
                name = "DOUBLE_BOTTOM",
                direction = PatternDirection.BULLISH,
                status = status,
                confirmIndex = confirmIdx,
                necklinePrice = neckline,
                entry = entry,
                stopLoss = stop,
                targets = listOf(round4(target1)),
                invalidation = buildString {
                    append("A candle CLOSES below the lower bottom ")
                    append(fmt2(lowerBottom))
                    append(" (spec §9: structural valley breakout)")
                },
                peakPrice = avgValley,
                swingIndices = Triple(valley1.index, peak.index, valley2.index),
                confidence = conf,
                notes = buildString {
                    append("time_gap_days=").append(spanDays(valley1.timeMillis, valley2.timeMillis).toLong())
                    append(", slippage=").append(fmt4pct(pctDiff(valley1.price, valley2.price)))
                    append(", target=measured_height (").append(fmt2(height)).append(')')
                },
            )
        }
        return hits
    }

    /** Run all pattern detectors and return combined hits (newest first). */
    fun detectPatterns(structure: SwingStructure, candles: List<Candle>, cfg: Cfg = Cfg()): List<StrictPatternHit> {
        val all = mutableListOf<StrictPatternHit>()
        all += detectDoubleTop(structure, candles, cfg)
        all += detectDoubleBottom(structure, candles, cfg)
        // H&S (§5-6) — stub: requires head-shoulder-shoulder geometry + trend filter;
        // ported from patterns_hs.py once the full Kotlin port of that module lands.
        // Cyclic (§10), Channel/Triangle (§11-15), Continuation (§16-25), Harmonics (§26-29)
        // are scheduled for Stage 6 follow-up and are NOT yet wired here.
        return all.sortedByDescending { it.confirmIndex ?: 0 }
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    /** First swing with a candle index strictly inside (lo, hi). */
    private fun between(swings: List<Swing>, lo: Int, hi: Int): Swing? =
        swings.firstOrNull { lo < it.index && it.index < hi }

    private fun pctDiff(a: Double, b: Double): Double {
        val mid = (a + b) / 2
        return if (mid != 0.0) abs(a - b) / mid else 0.0
    }

    /** days between two timestamps (millis → 86_400_000). */
    private fun spanDays(t1: Long, t2: Long): Double = abs(t2 - t1) / 86_400_000.0

    /** First candle index whose CLOSE has broken `level` for `consecutive` closes. */
    private fun findCloseBreak(
        candles: List<Candle>,
        start: Int,
        level: Double,
        direction: String,
        consecutive: Int,
    ): Int? {
        var seen = 0
        for (i in start until candles.size) {
            val close = candles[i].close
            val hit = if (direction == "below") close < level else close > level
            seen = if (hit) seen + 1 else 0
            if (seen >= consecutive) return i - consecutive + 1
        }
        return null
    }

    private fun anyCloseAbove(candles: List<Candle>, start: Int, level: Double): Boolean {
        for (i in start until candles.size) if (candles[i].close > level) return true
        return false
    }

    private fun anyCloseBelow(candles: List<Candle>, start: Int, level: Double): Boolean {
        for (i in start until candles.size) if (candles[i].close < level) return true
        return false
    }

    /**
     * Rule-satisfaction score in [0,1]. Tighter slippage + deeper valley → higher.
     * FORMING hits cap at 0.5; FULLY_FORMED / INVALIDATED are scored by geometry only.
     */
    fun confidence(slippageRatio: Double, depthRatio: Double, status: StrictPatternStatus): Double {
        val slipScore = maxOf(0.0, 1.0 - slippageRatio)
        val depthScore = minOf(1.0, depthRatio)
        var geo = 0.6 * slipScore + 0.4 * depthScore
        if (status == StrictPatternStatus.FORMING) geo *= 0.5
        return round3(maxOf(0.0, minOf(1.0, geo)))
    }

    /** Collapse consecutive same-side pivots to the most extreme (mirrors `_merge_same_side`). */
    private fun mergeSameSide(pivots: List<Pivot>): List<Pivot> {
        if (pivots.size < 2) return pivots
        val out = mutableListOf(pivots[0])
        for (p in pivots.drop(1)) {
            val prev = out.last()
            if (prev.side == p.side) {
                val moreExtreme = if (p.side == Side.UP) p.price > prev.price else p.price < prev.price
                if (moreExtreme) out[out.size - 1] = p // later bar is the more extreme swing
            } else {
                out += p
            }
        }
        return out
    }

    /** Classic structure rule over the last two swings of each polarity. */
    private fun trendFromSwings(highs: List<Swing>, lows: List<Swing>): PatternDirection {
        if (highs.size >= 2 && lows.size >= 2) {
            val lastHigh = highs[highs.size - 1].price
            val prevHigh = highs[highs.size - 2].price
            val lastLow = lows[lows.size - 1].price
            val prevLow = lows[lows.size - 2].price
            if (lastHigh > prevHigh && lastLow > prevLow) return PatternDirection.BULLISH
            if (lastHigh < prevHigh && lastLow < prevLow) return PatternDirection.BEARISH
        }
        return PatternDirection.NEUTRAL
    }

    // ── number formatting (mirror Python's round / f-strings) ─────────────────

    private fun round3(x: Double): Double = round(x * 1000.0) / 1000.0
    private fun round4(x: Double): Double = round(x * 10000.0) / 10000.0
    private fun fmt2(x: Double): String = String.format("%.2f", x)
    private fun fmt4pct(x: Double): String = String.format("%.4f", x * 100) + "%"
}
