package com.bofedge.domain.model

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Lifecycle status of a chart pattern. */
enum class PatternStatus {
    FORMING,
    FORMED,
    INVALIDATED,
}

/** Name of a detectable chart pattern. */
enum class ChartPatternName {
    TRENDLINE,
    SUPPORT_RESISTANCE,
    CHANNEL,
    ASCENDING_TRIANGLE,
    DESCENDING_TRIANGLE,
    SYMMETRICAL_TRIANGLE,
    HEAD_AND_SHOULDERS,
    INVERSE_HEAD_AND_SHOULDERS,
    BULL_FLAG,
    BEAR_FLAG,
}

/** A detected chart pattern. */
data class ChartPattern(
    val name: ChartPatternName,
    val direction: PatternDirection,
    val status: PatternStatus,
    val timeframe: Timeframe,
    val confidence: Double,
    val startTimestamp: Long,
    val endTimestamp: Long,
    val targetPrice: Double?,
    val description: String,
)

/** Configuration for chart pattern detection. */
data class ChartPatternConfig(
    val swingLookback: Int = 3,
    val tolerancePercent: Double = 0.01,
)

/** Engine for detecting chart patterns from candle data.
 *  Implementation is intentionally simple: it derives swing highs/lows and
 *  tests a small set of well-known pattern geometries against them.
 */
object ChartPatternEngine {

    /** Detect all chart patterns in the given candles (oldest to newest). */
    fun detectPatterns(
        candles: List<Candle>,
        config: ChartPatternConfig = ChartPatternConfig(),
    ): List<ChartPattern> {
        if (candles.size < config.swingLookback * 4 + 2) return emptyList()

        val swingsHigh = swingHighs(candles, config.swingLookback)
        val swingsLow = swingLows(candles, config.swingLookback)
        if (swingsHigh.isEmpty() || swingsLow.isEmpty()) return emptyList()

        return listOfNotNull(
            detectChannel(candles, swingsHigh, swingsLow),
            detectAscendingTriangle(candles, swingsHigh, swingsLow, config),
            detectDescendingTriangle(candles, swingsHigh, swingsLow, config),
            detectBullFlag(candles),
            detectBearFlag(candles),
        )
    }

    /** Indices of swing highs. */
    fun swingHighs(candles: List<Candle>, lookback: Int): List<Int> {
        val result = mutableListOf<Int>()
        for (i in lookback until candles.size - lookback) {
            val high = candles[i].high
            var isSwing = true
            for (j in 1..lookback) {
                if (candles[i - j].high > high || candles[i + j].high > high) {
                    isSwing = false
                    break
                }
            }
            if (isSwing) result.add(i)
        }
        return result
    }

    /** Indices of swing lows. */
    fun swingLows(candles: List<Candle>, lookback: Int): List<Int> {
        val result = mutableListOf<Int>()
        for (i in lookback until candles.size - lookback) {
            val low = candles[i].low
            var isSwing = true
            for (j in 1..lookback) {
                if (candles[i - j].low < low || candles[i + j].low < low) {
                    isSwing = false
                    break
                }
            }
            if (isSwing) result.add(i)
        }
        return result
    }

    private fun detectChannel(
        candles: List<Candle>,
        highs: List<Int>,
        lows: List<Int>,
    ): ChartPattern? {
        if (highs.size < 2 || lows.size < 2) return null

        val h1 = highs[highs.size - 2]; val h2 = highs.last()
        val l1 = lows[lows.size - 2]; val l2 = lows.last()

        val highSlope = slope(candles[h1].high, candles[h2].high, h2 - h1)
        val lowSlope = slope(candles[l1].low, candles[l2].low, l2 - l1)

        // Roughly parallel slopes => channel
        val reference = max(abs(highSlope), 1e-9)
        if (abs(highSlope - lowSlope) / reference > 0.35) return null

        val direction = when {
            highSlope > 0 -> PatternDirection.BULLISH
            highSlope < 0 -> PatternDirection.BEARISH
            else -> PatternDirection.NEUTRAL
        }

        return ChartPattern(
            name = ChartPatternName.CHANNEL,
            direction = direction,
            status = PatternStatus.FORMING,
            timeframe = candles.last().timeframe,
            confidence = 0.6,
            startTimestamp = candles[min(h1, l1)].timeMillis,
            endTimestamp = candles.last().timeMillis,
            targetPrice = null,
            description = "Parallel channel detected from recent swing highs/lows",
        )
    }

    private fun detectAscendingTriangle(
        candles: List<Candle>,
        highs: List<Int>,
        lows: List<Int>,
        config: ChartPatternConfig,
    ): ChartPattern? {
        if (highs.size < 2 || lows.size < 2) return null

        val h1 = highs[highs.size - 2]; val h2 = highs.last()
        val l1 = lows[lows.size - 2]; val l2 = lows.last()

        val flatResistance = areFlat(candles[h1].high, candles[h2].high, config.tolerancePercent)
        val risingLows = candles[l2].low > candles[l1].low

        if (!flatResistance || !risingLows) return null

        val resistance = (candles[h1].high + candles[h2].high) / 2
        val lastLow = candles[l2].low
        val target = resistance + (resistance - lastLow)

        return ChartPattern(
            name = ChartPatternName.ASCENDING_TRIANGLE,
            direction = PatternDirection.BULLISH,
            status = PatternStatus.FORMING,
            timeframe = candles.last().timeframe,
            confidence = 0.65,
            startTimestamp = candles[min(h1, l1)].timeMillis,
            endTimestamp = candles.last().timeMillis,
            targetPrice = target,
            description = "Ascending triangle: flat resistance near %.2f with rising lows".format(resistance),
        )
    }

    private fun detectDescendingTriangle(
        candles: List<Candle>,
        highs: List<Int>,
        lows: List<Int>,
        config: ChartPatternConfig,
    ): ChartPattern? {
        if (highs.size < 2 || lows.size < 2) return null

        val h1 = highs[highs.size - 2]; val h2 = highs.last()
        val l1 = lows[lows.size - 2]; val l2 = lows.last()

        val flatSupport = areFlat(candles[l1].low, candles[l2].low, config.tolerancePercent)
        val fallingHighs = candles[h2].high < candles[h1].high

        if (!flatSupport || !fallingHighs) return null

        val support = (candles[l1].low + candles[l2].low) / 2
        val lastHigh = candles[h2].high
        val target = support - (lastHigh - support)

        return ChartPattern(
            name = ChartPatternName.DESCENDING_TRIANGLE,
            direction = PatternDirection.BEARISH,
            status = PatternStatus.FORMING,
            timeframe = candles.last().timeframe,
            confidence = 0.65,
            startTimestamp = candles[min(h1, l1)].timeMillis,
            endTimestamp = candles.last().timeMillis,
            targetPrice = target,
            description = "Descending triangle: flat support near %.2f with falling highs".format(support),
        )
    }

    private fun detectBullFlag(candles: List<Candle>): ChartPattern? {
        val window = candles.takeLast(10)
        val poleRise = window[4].close / window[0].close - 1
        if (poleRise < 0.05) return null

        val consolidation = window.takeLast(4)
        val high = consolidation.maxOf { it.high }
        val low = consolidation.minOf { it.low }
        val range = high - low

        if (range <= 0) return null

        return ChartPattern(
            name = ChartPatternName.BULL_FLAG,
            direction = PatternDirection.BULLISH,
            status = PatternStatus.FORMING,
            timeframe = candles.last().timeframe,
            confidence = 0.55,
            startTimestamp = window[0].timeMillis,
            endTimestamp = candles.last().timeMillis,
            targetPrice = high + range,
            description = "Bull flag: sharp rally followed by tight consolidation",
        )
    }

    private fun detectBearFlag(candles: List<Candle>): ChartPattern? {
        val window = candles.takeLast(10)
        val poleFall = 1 - window[4].close / window[0].close
        if (poleFall < 0.05) return null

        val consolidation = window.takeLast(4)
        val high = consolidation.maxOf { it.high }
        val low = consolidation.minOf { it.low }
        val range = high - low

        if (range <= 0) return null

        return ChartPattern(
            name = ChartPatternName.BEAR_FLAG,
            direction = PatternDirection.BEARISH,
            status = PatternStatus.FORMING,
            timeframe = candles.last().timeframe,
            confidence = 0.55,
            startTimestamp = window[0].timeMillis,
            endTimestamp = candles.last().timeMillis,
            targetPrice = low - range,
            description = "Bear flag: sharp drop followed by tight consolidation",
        )
    }

    private fun slope(a: Double, b: Double, periods: Int): Double =
        if (periods > 0) (b - a) / periods else 0.0

    private fun areFlat(a: Double, b: Double, tolerancePercent: Double): Boolean {
        val ref = max(abs(a), 1e-9)
        return abs(b - a) / ref <= tolerancePercent
    }
}
