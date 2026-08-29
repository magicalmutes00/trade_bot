package com.bofedge.domain.model

/** Result of a screener evaluation for a single instrument. */
data class ScreenerResult(
    val instrument: Instrument,
    val timeframe: Timeframe,
    val direction: PatternDirection?,
    val pattern: ChartPatternName?,
    val patternStatus: PatternStatus?,
    val marketStructure: MarketStructure?,
    val candlestickPattern: CandlestickPattern?,
    val riskReward: RiskRewardResult?,
    val confidence: Double,
    val score: Double,
    val reason: String,
)

/** Direction filters for the screener. */
enum class ScreenerDirection {
    BULLISH,
    BEARISH,
    NEUTRAL,
    ANY,
}

/** Status filters for the screener. */
enum class ScreenerStatus {
    FORMING,
    FORMED,
    INVALIDATED,
    ANY,
}

/** Market universes for the screener. */
enum class ScreenerMarket {
    ALL,
    FNO,
    NIFTY,
    BANKNIFTY,
}

/** Configuration for screener filtering. */
data class ScreenerConfig(
    val direction: ScreenerDirection = ScreenerDirection.ANY,
    val status: ScreenerStatus = ScreenerStatus.ANY,
    val market: ScreenerMarket = ScreenerMarket.ALL,
    val timeframe: Timeframe = Timeframe.DAILY,
    val minConfidence: Double = 0.5,
    val minRiskRewardRatio: Double = 1.0,
    val limit: Int = 50,
)

/** Engine that combines the analysis engines and ranks instruments
 *  according to the configured filters.
 */
object ScreenerEngine {

    /** Run the screener over the given instrument/candle data, returning the
     *  matching results sorted by score (best first), limited to
     *  [ScreenerConfig.limit] entries.
     */
    fun screen(
        data: List<Pair<Instrument, List<Candle>>>,
        config: ScreenerConfig = ScreenerConfig(),
    ): List<ScreenerResult> {
        if (data.isEmpty()) return emptyList()

        return data
            .asSequence()
            .filter { marketMatches(it.first, config.market) }
            .mapNotNull { evaluateInstrument(it.first, it.second, config) }
            .sortedByDescending { it.score }
            .take(config.limit)
            .toList()
    }

    private fun marketMatches(instrument: Instrument, market: ScreenerMarket): Boolean = when (market) {
        ScreenerMarket.ALL -> true
        ScreenerMarket.FNO -> instrument.type == "STOCK" || instrument.type == "INDEX"
        ScreenerMarket.NIFTY -> instrument.exchange == "NSE" || instrument.type == "INDEX"
        ScreenerMarket.BANKNIFTY -> instrument.sectorName?.contains("BANK", ignoreCase = true) == true ||
            instrument.symbol.contains("BANK", ignoreCase = true)
    }

    private fun evaluateInstrument(
        instrument: Instrument,
        candles: List<Candle>,
        config: ScreenerConfig,
    ): ScreenerResult? {
        if (candles.size < of4) return null

        val structure = MarketStructureEngine.analyze(candles)
        val candlestick = CandlestickPatternEngine.detectPatterns(candles).lastOrNull()
        val chartPattern = ChartPatternEngine.detectPatterns(candles).maxByOrNull { it.confidence }

        // Direction filter
        val finalDirection: PatternDirection? = when (config.direction) {
            ScreenerDirection.BULLISH -> PatternDirection.BULLISH
            ScreenerDirection.BEARISH -> PatternDirection.BEARISH
            ScreenerDirection.NEUTRAL -> PatternDirection.NEUTRAL
            ScreenerDirection.ANY -> chartPattern?.direction
                ?: candlestick?.direction
                ?: structure.toPatternDirection()
        }

        if (config.direction != ScreenerDirection.ANY && finalDirection != null) {
            val matches = chartPattern?.direction == finalDirection ||
                candlestick?.direction == finalDirection ||
                structure.toPatternDirection() == finalDirection
            if (!matches) return null
        }

        // Status filter
        if (config.status != ScreenerStatus.ANY) {
            val required = when (config.status) {
                ScreenerStatus.FORMING -> PatternStatus.FORMING
                ScreenerStatus.FORMED -> PatternStatus.FORMED
                ScreenerStatus.INVALIDATED -> PatternStatus.INVALIDATED
                else -> null
            }
            if (required != null && chartPattern != null && chartPattern.status != required) return null
        }

        // Risk/reward estimate from support/resistance levels
        val riskReward = estimateRiskReward(candles.last(), structure)
        if (riskReward != null && riskReward.riskRewardRatio < config.minRiskRewardRatio) return null

        // Confidence filter
        val confidence = kotlin.math.max(
            chartPattern?.confidence ?: 0.0,
            kotlin.math.max(candlestick?.confidence ?: 0.0, structure.confidence),
        )
        if (confidence < config.minConfidence) return null

        val score = confidence * 60 +
            (riskReward?.riskRewardRatio ?: 0.0) * 10 +
            (if (chartPattern != null && chartPattern.status == PatternStatus.FORMED) 10.0 else 0.0)

        val reason = buildReasonOnly(structure, candlestick, chartPattern, riskReward)

        return ScreenerResult(
            instrument = instrument,
            timeframe = config.timeframe,
            direction = finalDirection,
            pattern = chartPattern?.name,
            patternStatus = chartPattern?.status,
            marketStructure = structure,
            candlestickPattern = candlestick,
            riskReward = riskReward,
            confidence = confidence,
            score = score,
            reason = reason,
        )
    }

    private const val of4: Int = 8 // minimum candles needed for a meaningful evaluation

    /** Estimate entry/stop/target from the latest close and the structure's
     *  nearest support/resistance. Returns null when levels are missing.
     */
    fun estimateRiskReward(candle: Candle, structure: MarketStructure): RiskRewardResult? {
        val resistance = structure.supportResistance.nearestResistance
        val support = structure.supportResistance.nearestSupport
        val lastClose = candle.close

        return when (structure.trend) {
            Trend.BULLISH -> {
                if (support == null || resistance == null) null
                else RiskRewardEngine.calculate(
                    entry = lastClose,
                    stopLoss = support,
                    target = resistance,
                )
            }
            Trend.BEARISH -> {
                if (support == null || resistance == null) null
                else RiskRewardEngine.calculate(
                    entry = lastClose,
                    stopLoss = resistance,
                    target = support,
                )
            }
            Trend.NEUTRAL -> null
        }
    }

    private fun buildReasonOnly(
        structure: MarketStructure,
        candlestick: CandlestickPattern?,
        chartPattern: ChartPattern?,
        riskReward: RiskRewardResult?,
    ): String {
        val parts = mutableListOf<String>()
        parts.add(structure.description)
        candlestick?.let { parts.add(it.description) }
        chartPattern?.let { parts.add(it.description) }
        riskReward?.let { parts.add("R:R = ${RiskRewardEngine.formatRatioDecimal(it.riskRewardRatio)}") }
        return parts.joinToString(". ")
    }

    private fun MarketStructure.toPatternDirection(): PatternDirection = when (trend) {
        Trend.BULLISH -> PatternDirection.BULLISH
        Trend.BEARISH -> PatternDirection.BEARISH
        Trend.NEUTRAL -> PatternDirection.NEUTRAL
    }
}
