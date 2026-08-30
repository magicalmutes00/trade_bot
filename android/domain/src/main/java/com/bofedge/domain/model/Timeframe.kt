package com.bofedge.domain.model

/** Timeframe for market data and analysis. */
enum class Timeframe(val code: String) {
    H4("4h"),
    DAILY("1D"),
    WEEKLY("1W"),
    MONTHLY("1M");

    override fun toString() = code
}
