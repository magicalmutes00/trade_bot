package com.bofedge.domain.model

/** One OHLCV bar for charting. `timeMillis` is UTC epoch milliseconds. */
data class Candle(
    val timeMillis: Long,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Long,
    val timeframe: Timeframe = Timeframe.DAILY,
) {
    val isBullish: Boolean get() = close >= open
}
