package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HeatmapCellDto(
    @SerialName("instrument_id") val instrumentId: String,
    @SerialName("symbol") val symbol: String,
    @SerialName("name") val name: String,
    @SerialName("instrument_type") val type: String,
    @SerialName("sector_name") val sectorName: String? = null,
    @SerialName("last_price") val lastPrice: Double? = null,
    @SerialName("change_pct") val changePct: Double? = null,
    @SerialName("bof_direction") val bofDirection: String? = null,
    @SerialName("bof_strength") val bofStrength: String? = null,
    @SerialName("bof_status") val bofStatus: String? = null,
    @SerialName("bof_timeframe") val bofTimeframe: String? = null,
)

@Serializable
data class HeatmapGroupDto(
    @SerialName("key") val key: String,
    @SerialName("label") val label: String,
    @SerialName("cells") val cells: List<HeatmapCellDto> = emptyList(),
)

@Serializable
data class HeatmapResponseDto(
    @SerialName("group_by") val groupBy: String = "sector",
    @SerialName("groups") val groups: List<HeatmapGroupDto> = emptyList(),
)

@Serializable
data class WatchlistItemDto(
    @SerialName("instrument_id") val instrumentId: String,
    @SerialName("symbol") val symbol: String,
    @SerialName("name") val name: String,
    @SerialName("instrument_type") val type: String,
    @SerialName("sector_name") val sectorName: String? = null,
    @SerialName("position") val position: Int = 0,
    @SerialName("alert_enabled") val alertEnabled: Boolean = false,
    @SerialName("last_price") val lastPrice: Double? = null,
    @SerialName("change_pct") val changePct: Double? = null,
    @SerialName("bof_direction") val bofDirection: String? = null,
    @SerialName("bof_strength") val bofStrength: String? = null,
    @SerialName("bof_status") val bofStatus: String? = null,
)

@Serializable
data class WatchlistDto(
    @SerialName("id") val id: String,
    @SerialName("name") val name: String,
    @SerialName("items") val items: List<WatchlistItemDto> = emptyList(),
)

@Serializable
data class SignalStatsDetailedDto(
    @SerialName("total_signals") val totalSignals: Int = 0,
    @SerialName("bullish") val bullish: Int = 0,
    @SerialName("bearish") val bearish: Int = 0,
    @SerialName("confirmed") val confirmed: Int = 0,
    @SerialName("invalidated") val invalidated: Int = 0,
    @SerialName("detecting") val detecting: Int = 0,
    @SerialName("avg_confidence") val avgConfidence: Double? = null,
    @SerialName("confirmation_rate") val confirmationRate: Double? = null,
)

@Serializable
data class CreateWatchlistRequestDto(
    @SerialName("name") val name: String,
)

@Serializable
data class RenameWatchlistRequestDto(
    @SerialName("name") val name: String,
)

@Serializable
data class AddWatchlistItemRequestDto(
    @SerialName("instrument_id") val instrumentId: String,
    @SerialName("alert_enabled") val alertEnabled: Boolean = false,
)

@Serializable
data class UpdateWatchlistItemRequestDto(
    @SerialName("alert_enabled") val alertEnabled: Boolean? = null,
    @SerialName("position") val position: Int? = null,
)

@Serializable
data class CandleDto(
    @SerialName("timeframe") val timeframe: String = "15m",
    @SerialName("ts") val ts: String,
    @SerialName("open") val open: String,
    @SerialName("high") val high: String,
    @SerialName("low") val low: String,
    @SerialName("close") val close: String,
    @SerialName("volume") val volume: Long? = null,
)

@Serializable
data class PaginatedCandlesDto(
    @SerialName("items") val items: List<CandleDto> = emptyList(),
    @SerialName("timeframe") val timeframe: String = "15m",
    @SerialName("has_more") val hasMore: Boolean = false,
)
