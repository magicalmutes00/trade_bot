package com.bofedge.domain.model

/** Dashboard aggregate (Phase 2): real status, honest empty signal feeds. */
data class MarketStatusInfo(
    val market: String,
    val status: String,      // OPEN | PRE_OPEN | CLOSED | HALF_DAY | HOLIDAY
)

data class BofSummary(
    val activeTotal: Int,
    val bullish: Int,
    val bearish: Int,
    val strong: Int,
    val newToday: Int,
    val detectedToday: Int,
)

data class IndexQuote(
    val instrumentId: String,
    val symbol: String,
    val name: String,
    val lastPrice: Double?,
    val changePct: Double?,
    val direction: String?,
)

/** Compact BOF signal card for dashboard feeds. */
data class SignalCard(
    val id: String,
    val instrumentId: String,
    val symbol: String,
    val direction: String,     // BULLISH | BEARISH
    val strength: String,      // WEAK | MODERATE | STRONG | VERY_STRONG
    val status: String,
    val bofLevel: Double,
    val confidence: Double,
    val timeframe: String,
    val detectedAt: String,
)

data class DashboardSnapshot(
    val marketStatus: MarketStatusInfo,
    val bofSummary: BofSummary,
    val indices: List<IndexQuote>,
    val latestSignals: List<SignalCard>,
    val strongestSignals: List<SignalCard>,
)
