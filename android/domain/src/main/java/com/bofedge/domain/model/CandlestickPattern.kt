package com.bofedge.domain.model

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Direction of a pattern. */
enum class PatternDirection {
    BULLISH,
    BEARISH,
    NEUTRAL,
}

/** Result of a candlestick pattern detection. */
data class CandlestickPattern(
    val pattern: PatternName,
    val direction: PatternDirection,
    val timestamp: Long,     // timeMillis of the pattern candle
    val timeframe: Timeframe,
    val confidence: Double,  // 0.0 to 1.0
    val description: String,
)

/** Name of a detectable candlestick pattern. */
enum class PatternName {
    DOJI,
    HAMMER,
    INVERTED_HAMMER,
    SHOOTING_STAR,
    BULLISH_ENGULFING,
    BEARISH_ENGULFING,
    MORNING_STAR,
    EVENING_STAR,
    MARUBOZU,
}

/** Parameters for candlestick pattern detection. */
data class CandlestickPatternConfig(
    val dojiWickBodyRatio: Double = 0.1,
    val hammerBodyLowerRatio: Double = 0.3,
    val engulfingBodyRatio: Double = 0.5,
    val starGapThreshold: Double = 0.001,
    val minBodySizeRatio: Double = 0.1,
)

/** Engine for detecting candlestick patterns from candle data. */
object CandlestickPatternEngine {

    /** Detect all candlestick patterns in a list of candles.
     *  Candles should be in chronological order (oldest to newest).
     */
    fun detectPatterns(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): List<CandlestickPattern> {
        if (candles.size < 2) return emptyList()

        return listOfNotNull(
            detectDoji(candles, config),
            detectHammer(candles, config),
            detectInvertedHammer(candles, config),
            detectShootingStar(candles, config),
            detectBullishEngulfing(candles, config),
            detectBearishEngulfing(candles, config),
            detectMorningStar(candles, config),
            detectEveningStar(candles, config),
            detectMarubozu(candles, config),
        )
    }

    /** Detect Doji: small body, long wicks on both sides. */
    fun detectDoji(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        val c = candles.last()

        val bodySize = abs(c.close - c.open)
        val totalRange = c.high - c.low
        val wickTop = c.high - max(c.open, c.close)
        val wickBottom = min(c.open, c.close) - c.low

        val bodyToRangeRatio = if (totalRange > 0) bodySize / totalRange else 1.0
        val isDoji = bodyToRangeRatio <= config.dojiWickBodyRatio

        if (!isDoji) return null

        val avgWick = (wickTop + wickBottom) / 2 / max(totalRange, 1e-9)
        val hasLongWicks = avgWick >= 0.5

        return if (hasLongWicks) {
            CandlestickPattern(
                pattern = PatternName.DOJI,
                direction = PatternDirection.NEUTRAL,
                timestamp = c.timeMillis,
                timeframe = c.timeframe,
                confidence = 0.8,
                description = "Doji candlestick: market indecision, open and close are nearly equal",
            )
        } else null
    }

    /** Detect Hammer: small body at top, long lower shadow. */
    fun detectHammer(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        val c = candles.last()

        val bodySize = abs(c.close - c.open)
        val totalRange = c.high - c.low
        val lowerShadow = min(c.open, c.close) - c.low
        val upperShadow = c.high - max(c.open, c.close)

        val isHammer = bodySize > 0 &&
            totalRange > 0 &&
            lowerShadow >= bodySize * 2 &&
            upperShadow <= bodySize * 0.1

        if (!isHammer) return null

        val shadowToBodyRatio = lowerShadow / bodySize
        val confidence = min(0.5 + shadowToBodyRatio * 0.15, 0.95)

        return CandlestickPattern(
            pattern = PatternName.HAMMER,
            direction = PatternDirection.BULLISH,
            timestamp = c.timeMillis,
            timeframe = c.timeframe,
            confidence = confidence,
            description = "Hammer candlestick: bullish reversal pattern with long lower shadow",
        )
    }

    /** Detect Inverted Hammer: small body at bottom, long upper shadow. */
    fun detectInvertedHammer(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        val c = candles.last()

        val bodySize = abs(c.close - c.open)
        val totalRange = c.high - c.low
        val lowerShadow = min(c.open, c.close) - c.low
        val upperShadow = c.high - max(c.open, c.close)

        val isInvertedHammer = bodySize > 0 &&
            totalRange > 0 &&
            upperShadow >= bodySize * 2 &&
            lowerShadow <= bodySize * 0.1

        if (!isInvertedHammer) return null

        val shadowToBodyRatio = upperShadow / bodySize
        val confidence = min(0.5 + shadowToBodyRatio * 0.15, 0.95)

        return CandlestickPattern(
            pattern = PatternName.INVERTED_HAMMER,
            direction = PatternDirection.BULLISH,
            timestamp = c.timeMillis,
            timeframe = c.timeframe,
            confidence = confidence,
            description = "Inverted Hammer candlestick: bullish reversal with long upper shadow",
        )
    }

    /** Detect Shooting Star: small body at bottom, long upper shadow (bearish). */
    fun detectShootingStar(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        val c = candles.last()

        val bodySize = abs(c.close - c.open)
        val totalRange = c.high - c.low
        val lowerShadow = min(c.open, c.close) - c.low
        val upperShadow = c.high - max(c.open, c.close)

        val isShootingStar = bodySize > 0 &&
            totalRange > 0 &&
            upperShadow >= bodySize * 2 &&
            lowerShadow <= bodySize * 0.1

        if (!isShootingStar) return null

        val shadowToBodyRatio = upperShadow / bodySize
        val confidence = min(0.5 + shadowToBodyRatio * 0.15, 0.95)

        return CandlestickPattern(
            pattern = PatternName.SHOOTING_STAR,
            direction = PatternDirection.BEARISH,
            timestamp = c.timeMillis,
            timeframe = c.timeframe,
            confidence = confidence,
            description = "Shooting Star candlestick: bearish reversal with long upper shadow",
        )
    }

    /** Detect Bullish Engulfing: current bullish body engulfs previous bearish body. */
    fun detectBullishEngulfing(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        if (candles.size < 2) return null
        val prev = candles[candles.size - 2]
        val curr = candles[candles.size - 1]

        val prevIsBearish = prev.close < prev.open
        val currIsBullish = curr.close > curr.open

        if (!prevIsBearish || !currIsBullish) return null

        val prevBodySize = abs(prev.close - prev.open)
        val currBodySize = abs(curr.close - curr.open)
        val engulfs = curr.open <= prev.close && curr.close >= prev.open &&
            currBodySize >= prevBodySize * config.engulfingBodyRatio

        if (!engulfs) return null

        var confidence = 0.7
        val bodyRatio = if (prevBodySize > 0) currBodySize / prevBodySize else 1.0
        if (bodyRatio > 1.5) confidence = 0.9

        return CandlestickPattern(
            pattern = PatternName.BULLISH_ENGULFING,
            direction = PatternDirection.BULLISH,
            timestamp = curr.timeMillis,
            timeframe = curr.timeframe,
            confidence = confidence,
            description = "Bullish Engulfing candlestick: bullish body engulfs previous bearish body",
        )
    }

    /** Detect Bearish Engulfing: current bearish body engulfs previous bullish body. */
    fun detectBearishEngulfing(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        if (candles.size < 2) return null
        val prev = candles[candles.size - 2]
        val curr = candles[candles.size - 1]

        val prevIsBullish = prev.close > prev.open
        val currIsBearish = curr.close < curr.open

        if (!prevIsBullish || !currIsBearish) return null

        val prevBodySize = abs(prev.close - prev.open)
        val currBodySize = abs(curr.close - curr.open)
        val engulfs = curr.open >= prev.close && curr.close <= prev.open &&
            currBodySize >= prevBodySize * config.engulfingBodyRatio

        if (!engulfs) return null

        var confidence = 0.7
        val bodyRatio = if (prevBodySize > 0) currBodySize / prevBodySize else 1.0
        if (bodyRatio > 1.5) confidence = 0.9

        return CandlestickPattern(
            pattern = PatternName.BEARISH_ENGULFING,
            direction = PatternDirection.BEARISH,
            timestamp = curr.timeMillis,
            timeframe = curr.timeframe,
            confidence = confidence,
            description = "Bearish Engulfing candlestick: bearish body engulfs previous bullish body",
        )
    }

    /** Detect Morning Star: three-candle bullish reversal (bearish, small body, bullish). */
    fun detectMorningStar(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        if (candles.size < 3) return null
        val third = candles[candles.size - 3]
        val second = candles[candles.size - 2]
        val first = candles[candles.size - 1]

        val firstIsBullish = first.close > first.open
        val secondBodySize = abs(second.close - second.open)
        val secondTotalRange = second.high - second.low
        val isSecondSmall = secondBodySize / max(secondTotalRange, 1e-9) <= 0.3
        val thirdIsBearish = third.close < third.open

        if (!(firstIsBullish && isSecondSmall && thirdIsBearish)) return null

        return CandlestickPattern(
            pattern = PatternName.MORNING_STAR,
            direction = PatternDirection.BULLISH,
            timestamp = first.timeMillis,
            timeframe = first.timeframe,
            confidence = 0.8,
            description = "Morning Star candlestick: three-candle bullish reversal pattern",
        )
    }

    /** Detect Evening Star: three-candle bearish reversal (bullish, small body, bearish). */
    fun detectEveningStar(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        if (candles.size < 3) return null
        val third = candles[candles.size - 3]
        val second = candles[candles.size - 2]
        val first = candles[candles.size - 1]

        val firstIsBearish = first.close < first.open
        val secondBodySize = abs(second.close - second.open)
        val secondTotalRange = second.high - second.low
        val isSecondSmall = secondBodySize / max(secondTotalRange, 1e-9) <= 0.3
        val thirdIsBullish = third.close > third.open

        if (!(firstIsBearish && isSecondSmall && thirdIsBullish)) return null

        return CandlestickPattern(
            pattern = PatternName.EVENING_STAR,
            direction = PatternDirection.BEARISH,
            timestamp = first.timeMillis,
            timeframe = first.timeframe,
            confidence = 0.8,
            description = "Evening Star candlestick: three-candle bearish reversal pattern",
        )
    }

    /** Detect Marubozu: candle with no (or very small) wicks. */
    fun detectMarubozu(
        candles: List<Candle>,
        config: CandlestickPatternConfig = CandlestickPatternConfig(),
    ): CandlestickPattern? {
        val c = candles.last()

        val bodySize = abs(c.close - c.open)
        val totalRange = c.high - c.low
        val lowerShadow = min(c.open, c.close) - c.low
        val upperShadow = c.high - max(c.open, c.close)

        val isMarubozu = totalRange > 0 && bodySize > 0 &&
            lowerShadow <= bodySize * config.dojiWickBodyRatio &&
            upperShadow <= bodySize * config.dojiWickBodyRatio

        if (!isMarubozu) return null

        val isBullish = c.close >= c.open

        return CandlestickPattern(
            pattern = PatternName.MARUBOZU,
            direction = if (isBullish) PatternDirection.BULLISH else PatternDirection.BEARISH,
            timestamp = c.timeMillis,
            timeframe = c.timeframe,
            confidence = 0.85,
            description = "${if (isBullish) "Bullish" else "Bearish"} Marubozu: full-body candle with no meaningful wicks",
        )
    }
}
