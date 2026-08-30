package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** TRADEBOT strict pattern engine response for one instrument (spec §35). */
@Serializable
data class InstrumentPatternsDto(
    @SerialName("instrument_id") val instrumentId: String,
    @SerialName("symbol") val symbol: String = "",
    @SerialName("name") val name: String = "",
    @SerialName("scanned_at") val scannedAt: String? = null,
    @SerialName("timeframes") val timeframes: List<PatternDto> = emptyList(),
)

/** One timeframe's pattern state — mirrors backend PatternResponse exactly. */
@Serializable
data class PatternDto(
    @SerialName("timeframe") val timeframe: String,
    @SerialName("pattern_detected") val patternDetected: String = "None",
    @SerialName("status") val status: String = "Forming",
    @SerialName("direction") val direction: String = "Neutral",
    @SerialName("confidence") val confidence: Double = 0.0,
    @SerialName("entry") val entry: String? = null,
    @SerialName("stop_loss") val stopLoss: String? = null,
    @SerialName("target_1") val target1: String? = null,
    @SerialName("target_2") val target2: String? = null,
    @SerialName("target_3") val target3: String? = null,
    @SerialName("invalidation") val invalidation: String? = null,
    @SerialName("additional_notes") val additionalNotes: String? = null,
    @SerialName("reasoning") val reasoning: String? = null,
    @SerialName("neckline_price") val necklinePrice: Double? = null,
    @SerialName("peak_price") val peakPrice: Double? = null,
    @SerialName("swing_indices") val swingIndices: List<Int> = emptyList(),
    @SerialName("confirm_index") val confirmIndex: Int? = null,
    @SerialName("detected_at") val detectedAt: String? = null,
)