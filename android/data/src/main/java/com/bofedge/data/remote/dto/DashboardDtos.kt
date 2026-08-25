package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class MarketStatusDto(
    @SerialName("market") val market: String = "NSE",
    @SerialName("status") val status: String = "CLOSED",
    @SerialName("as_of") val asOf: String? = null,
)

@Serializable
data class BofSummaryDto(
    @SerialName("active_total") val activeTotal: Int = 0,
    @SerialName("bullish") val bullish: Int = 0,
    @SerialName("bearish") val bearish: Int = 0,
    @SerialName("strong") val strong: Int = 0,
    @SerialName("new_today") val newToday: Int = 0,
    @SerialName("detected_today") val detectedToday: Int = 0,
)

@Serializable
data class IndexQuoteDto(
    @SerialName("instrument_id") val instrumentId: String,
    @SerialName("symbol") val symbol: String,
    @SerialName("name") val name: String,
    @SerialName("last_price") val lastPrice: Double? = null,
    @SerialName("change_pct") val changePct: Double? = null,
    @SerialName("direction") val direction: String? = null,
)

@Serializable
data class SignalCardDto(
    @SerialName("id") val id: String,
    @SerialName("instrument_id") val instrumentId: String,
    @SerialName("symbol") val symbol: String,
    @SerialName("direction") val direction: String,
    @SerialName("strength") val strength: String,
    @SerialName("status") val status: String = "DETECTING",
    @SerialName("bof_level") val bofLevel: Double = 0.0,
    @SerialName("confidence") val confidence: Double = 0.0,
    @SerialName("timeframe") val timeframe: String = "15m",
    @SerialName("detected_at") val detectedAt: String? = null,
)

@Serializable
data class DashboardDto(
    @SerialName("market_status") val marketStatus: MarketStatusDto = MarketStatusDto(),
    @SerialName("bof_summary") val bofSummary: BofSummaryDto = BofSummaryDto(),
    @SerialName("indices") val indices: List<IndexQuoteDto> = emptyList(),
    @SerialName("latest_signals") val latestSignals: List<SignalCardDto> = emptyList(),
    @SerialName("strongest_signals") val strongestSignals: List<SignalCardDto> = emptyList(),
)
