package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PageDto<T>(
    @SerialName("items") val items: List<T> = emptyList(),
    @SerialName("total") val total: Int = 0,
    @SerialName("limit") val limit: Int = 0,
    @SerialName("offset") val offset: Int = 0,
)

@Serializable
data class InstrumentDto(
    @SerialName("id") val id: String,
    @SerialName("symbol") val symbol: String,
    @SerialName("name") val name: String,
    @SerialName("instrument_type") val type: String,
    @SerialName("exchange") val exchange: String,
    @SerialName("currency") val currency: String,
    @SerialName("sector_name") val sectorName: String? = null,
)

@Serializable
data class QuoteDto(
    // Backend serialises Decimal as JSON strings; isLenient handles both forms.
    @SerialName("last_price") val lastPrice: String? = null,
    @SerialName("change") val change: String? = null,
    @SerialName("change_pct") val changePct: String? = null,
    @SerialName("volume") val volume: Long? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class SignalStatsDto(
    @SerialName("total_signals") val totalSignals: Int = 0,
    @SerialName("bullish") val bullish: Int = 0,
    @SerialName("bearish") val bearish: Int = 0,
    @SerialName("confirmed") val confirmed: Int = 0,
    @SerialName("invalidated") val invalidated: Int = 0,
)

@Serializable
data class InstrumentDetailDto(
    @SerialName("id") val id: String,
    @SerialName("symbol") val symbol: String,
    @SerialName("name") val name: String,
    @SerialName("instrument_type") val type: String,
    @SerialName("exchange") val exchange: String,
    @SerialName("currency") val currency: String,
    @SerialName("sector_name") val sectorName: String? = null,
    @SerialName("tick_size") val tickSize: String? = null,
    @SerialName("lot_size") val lotSize: Int? = null,
    @SerialName("quote") val quote: QuoteDto? = null,
    @SerialName("stats") val stats: SignalStatsDto = SignalStatsDto(),
)
