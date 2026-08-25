package com.bofedge.domain.model

/** Instrument reference data (symbol/name/sector are real facts, never prices). */
data class Instrument(
    val id: String,
    val symbol: String,
    val name: String,
    val type: String,        // STOCK | INDEX | COMMODITY | FOREX | CRYPTO
    val exchange: String,
    val currency: String,
    val sectorName: String?,
)

data class SignalStats(
    val totalSignals: Int = 0,
    val bullish: Int = 0,
    val bearish: Int = 0,
    val confirmed: Int = 0,
    val invalidated: Int = 0,
) {
    val hasAny: Boolean get() = totalSignals > 0
}

data class InstrumentQuote(
    val lastPrice: Double?,
    val change: Double?,
    val changePct: Double?,
    val volume: Long?,
    val updatedAt: String?,
)

data class InstrumentDetail(
    val id: String,
    val symbol: String,
    val name: String,
    val type: String,
    val exchange: String,
    val currency: String,
    val sectorName: String?,
    val tickSize: Double?,
    val lotSize: Int?,
    val quote: InstrumentQuote?,
    val stats: SignalStats,
)

data class PageResult<T>(
    val items: List<T>,
    val total: Int,
    val offset: Int,
) {
    val endReached: Boolean get() = offset + items.size >= total
}
