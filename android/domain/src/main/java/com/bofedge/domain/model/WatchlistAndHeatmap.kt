package com.bofedge.domain.model

/** Heatmap cell — quote + current BOF state (nulls = no data yet). */
data class HeatmapCell(
    val instrumentId: String,
    val symbol: String,
    val name: String,
    val type: String,
    val sectorName: String?,
    val lastPrice: Double?,
    val changePct: Double?,
    val bofDirection: String?,
    val bofStrength: String?,
    val bofStatus: String?,
)

data class HeatmapGroup(
    val key: String,
    val label: String,
    val cells: List<HeatmapCell>,
)

/** Watchlist item enriched with quote + BOF state. */
data class WatchlistEntry(
    val instrumentId: String,
    val symbol: String,
    val name: String,
    val type: String,
    val sectorName: String?,
    val position: Int,
    val alertEnabled: Boolean,
    val lastPrice: Double?,
    val changePct: Double?,
    val bofDirection: String?,
    val bofStrength: String?,
    val bofStatus: String?,
)

data class Watchlist(
    val id: String,
    val name: String,
    val entries: List<WatchlistEntry>,
)

/** Detailed signal statistics for one instrument (Phase 5 history). */
data class SignalStatsDetailed(
    val totalSignals: Int = 0,
    val bullish: Int = 0,
    val bearish: Int = 0,
    val confirmed: Int = 0,
    val invalidated: Int = 0,
    val detecting: Int = 0,
    val avgConfidence: Double? = null,
    val confirmationRate: Double? = null,
)
