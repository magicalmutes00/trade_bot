package com.bofedge.domain.model

/** Overall market trend classification. */
enum class Trend {
    BULLISH,
    BEARISH,
    NEUTRAL,
}

/** Direction of a detected swing point. */
enum class SwingPointDirection {
    HIGH,
    LOW,
}

/** A detected swing point on the chart. */
data class SwingPoint(
    val index: Int,
    val price: Double,
    val timestamp: Long,
    val direction: SwingPointDirection,
)

/** Support and resistance levels derived from swing points. */
data class SupportResistance(
    val pivotHighs: List<Double>,
    val pivotLows: List<Double>,
    val nearestResistance: Double?,
    val nearestSupport: Double?,
)

/** Result of a market structure analysis. */
data class MarketStructure(
    val trend: Trend,
    val confidence: Double,
    val swingPoints: List<SwingPoint>,
    val supportResistance: SupportResistance,
    val description: String,
)

/** Configuration for swing detection. */
data class SwingDetectionConfig(
    val swingLookback: Int = 3,
    val minSwingDistance: Int = 2,
)

/** Engine that classifies market structure (HH/HL vs LH/LL) and derives
 *  swing points and support/resistance levels.
 */
object MarketStructureEngine {

    /** Analyse the given candles (oldest to newest). */
    fun analyze(
        candles: List<Candle>,
        config: SwingDetectionConfig = SwingDetectionConfig(),
    ): MarketStructure {
        if (candles.size < 2) {
            return MarketStructure(
                trend = Trend.NEUTRAL,
                confidence = 0.0,
                swingPoints = emptyList(),
                supportResistance = SupportResistance(
                    pivotHighs = emptyList(),
                    pivotLows = emptyList(),
                    nearestResistance = null,
                    nearestSupport = null,
                ),
                description = "Not enough candle data to analyse market structure",
            )
        }

        val swingPoints = detectSwingPoints(candles, config)
        val trend = classifyTrend(candles)
        val confidence = trendConfidence(candles, trend)
        val sr = buildSupportResistance(candles, swingPoints)

        return MarketStructure(
            trend = trend,
            confidence = confidence,
            swingPoints = swingPoints,
            supportResistance = sr,
            description = describe(trend, confidence),
        )
    }

    /** Detect swing highs/lows. Interior strict extremes are always included;
     *  in addition the global highest-high and lowest-low indices are added so
     *  the result contains both directions even in strongly trending data.
     */
    fun detectSwingPoints(candles: List<Candle>, config: SwingDetectionConfig): List<SwingPoint> {
        val lookback = config.swingLookback.coerceAtLeast(1)
        val points = mutableListOf<SwingPoint>()

        for (i in lookback until candles.size - lookback) {
            var isHigh = true
            var isLow = true
            for (j in 1..lookback) {
                if (candles[i - j].high > candles[i].high || candles[i + j].high > candles[i].high) isHigh = false
                if (candles[i - j].low < candles[i].low || candles[i + j].low < candles[i].low) isLow = false
            }
            if (isHigh) points.add(SwingPoint(i, candles[i].high, candles[i].timeMillis, SwingPointDirection.HIGH))
            if (isLow) points.add(SwingPoint(i, candles[i].low, candles[i].timeMillis, SwingPointDirection.LOW))
        }

        // Always include the global extremes so both directions are represented.
        val maxHighIdx = candles.indices.maxBy { candles[it].high }
        val minLowIdx = candles.indices.minBy { candles[it].low }
        if (points.none { it.direction == SwingPointDirection.HIGH && it.index == maxHighIdx }) {
            points.add(SwingPoint(maxHighIdx, candles[maxHighIdx].high, candles[maxHighIdx].timeMillis, SwingPointDirection.HIGH))
        }
        if (points.none { it.direction == SwingPointDirection.LOW && it.index == minLowIdx }) {
            points.add(SwingPoint(minLowIdx, candles[minLowIdx].low, candles[minLowIdx].timeMillis, SwingPointDirection.LOW))
        }

        return points.sortedBy { it.index }
    }

    /** Classify the trend by measuring how consistently highs and lows
     *  move in one direction from bar to bar. */
    private fun classifyTrend(candles: List<Candle>): Trend {
        var up = 0
        var down = 0
        for (i in 1 until candles.size) {
            val hh = candles[i].high > candles[i - 1].high
            val hl = candles[i].low > candles[i - 1].low
            val lh = candles[i].high < candles[i - 1].high
            val ll = candles[i].low < candles[i - 1].low
            if (hh && hl) up++
            if (lh && ll) down++
        }

        val total = (candles.size - 1).coerceAtLeast(1)
        val upFraction = up.toDouble() / total
        val downFraction = down.toDouble() / total

        return when {
            upFraction >= 0.6 -> Trend.BULLISH
            downFraction >= 0.6 -> Trend.BEARISH
            else -> Trend.NEUTRAL
        }
    }

    private fun trendConfidence(candles: List<Candle>, trend: Trend): Double {
        if (trend == Trend.NEUTRAL) return 0.3

        var up = 0
        var down = 0
        for (i in 1 until candles.size) {
            val hh = candles[i].high > candles[i - 1].high
            val hl = candles[i].low > candles[i - 1].low
            val lh = candles[i].high < candles[i - 1].high
            val ll = candles[i].low < candles[i - 1].low
            if (hh && hl) up++
            if (lh && ll) down++
        }
        val total = (candles.size - 1).coerceAtLeast(1)
        val fraction = if (trend == Trend.BULLISH) up.toDouble() / total else down.toDouble() / total
        return 0.5 + fraction * 0.4
    }

    private fun buildSupportResistance(
        candles: List<Candle>,
        swingPoints: List<SwingPoint>,
    ): SupportResistance {
        val pivotHighs = swingPoints
            .filter { it.direction == SwingPointDirection.HIGH }
            .map { it.price }
            .distinct()
            .sortedDescending()
        val pivotLows = swingPoints
            .filter { it.direction == SwingPointDirection.LOW }
            .map { it.price }
            .distinct()
            .sorted()

        val lastClose = candles.last().close
        val nearestResistance = pivotHighs.firstOrNull { it > lastClose }
        val nearestSupport = pivotLows.lastOrNull { it < lastClose }

        return SupportResistance(
            pivotHighs = pivotHighs,
            pivotLows = pivotLows,
            nearestResistance = nearestResistance,
            nearestSupport = nearestSupport,
        )
    }

    private fun describe(trend: Trend, confidence: Double): String = when (trend) {
        Trend.BULLISH -> "Market structure is bullish (higher highs and higher lows), confidence %.0f%%".format(confidence * 100)
        Trend.BEARISH -> "Market structure is bearish (lower lows and lower highs), confidence %.0f%%".format(confidence * 100)
        Trend.NEUTRAL -> "Market structure is neutral / ranging"
    }
}
