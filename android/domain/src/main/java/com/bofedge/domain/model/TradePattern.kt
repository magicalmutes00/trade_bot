package com.bofedge.domain.model

/** Lifecycle status of a server-side strict pattern (TRADEBOT spec §4). */
enum class TradePatternStatus(val wire: String) {
    FORMING("FORMING"),
    FULLY_FORMED("FULLY_FORMED"),
    INVALIDATED("INVALIDATED");

    companion object {
        fun fromWire(value: String?): TradePatternStatus? = entries.firstOrNull { it.wire == value }
    }
}

/**
 * A strict multi-timeframe pattern hit produced by the backend engine
 * (`GET /instruments/{id}/patterns`, spec §35 shape). Prices arrive as
 * formatted strings so method labels like "measured height" survive the wire.
 */
data class TradePattern(
    val timeframe: String,                 // wire timeframe code ("4h","1D","1W","1M")
    val patternDetected: String,           // "DOUBLE_TOP" | "Forming - DOUBLE_TOP" | "None"
    val status: TradePatternStatus,
    val direction: PatternDirection?,
    val confidence: Double,                // 0.0–1.0 rule-satisfaction score
    val entry: String?,
    val stopLoss: String?,
    val target1: String?,
    val target2: String?,
    val target3: String?,
    val invalidation: String?,
    val additionalNotes: String?,
    val reasoning: String?,
    // machine-readable extras for chart markers / the mobile engine
    val necklinePrice: Double?,            // bof_level / neckline
    val peakPrice: Double?,
    val swingIndices: List<Int>,
    val confirmIndex: Int?,
    val detectedAt: String?,               // ISO-8601 UTC
) {
    val hasDetectedPattern: Boolean get() = patternDetected != "None"

    val isFormed: Boolean get() = status == TradePatternStatus.FULLY_FORMED

    val isBullish: Boolean get() = direction == PatternDirection.BULLISH

    /** A numeric price usable as a marker line, preferring the neckline. */
    val markerPrice: Double? = necklinePrice ?: entry?.trim()?.toDoubleOrNull()
}