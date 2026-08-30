package com.bofedge.domain.repository

import com.bofedge.domain.model.Candle
import com.bofedge.domain.model.CandlestickPattern
import com.bofedge.domain.model.ChartPattern
import com.bofedge.domain.model.DashboardSnapshot
import com.bofedge.domain.model.HeatmapGroup
import com.bofedge.domain.model.Instrument
import com.bofedge.domain.model.InstrumentDetail
import com.bofedge.domain.model.MarketStructure
import com.bofedge.domain.model.PageResult
import com.bofedge.domain.model.SignalStatsDetailed
import com.bofedge.domain.model.Timeframe
import com.bofedge.domain.model.TradePattern
import com.bofedge.domain.result.ApiResult

/** Scanner sorts supported by the backend in Phase 2. */
enum class InstrumentSort(val wire: String) {
    SYMBOL("symbol"),
    NAME("name"),
    CHANGE_PCT("change_pct"),
    VOLUME("volume"),
}

interface InstrumentRepository {
    suspend fun search(
        query: String?,
        type: String?,
        sort: InstrumentSort,
        limit: Int,
        offset: Int,
    ): ApiResult<PageResult<Instrument>>

    suspend fun detail(id: String): ApiResult<InstrumentDetail>

    suspend fun dashboard(): ApiResult<DashboardSnapshot>

    /** Phase 5 — heatmap grid grouped server-side. */
    suspend fun heatmap(
        groupBy: String = "sector",
        type: String? = null,
        onlyWithSignals: Boolean = false,
    ): ApiResult<List<HeatmapGroup>>

    /** Phase 5 — detailed signal statistics for one instrument. */
    suspend fun signalStats(id: String): ApiResult<SignalStatsDetailed>

    /** Phase 10 — candlestick pattern detection. */
    suspend fun candlestickPatterns(id: String, timeframe: Timeframe): ApiResult<List<CandlestickPattern>>

    /** Phase 10 — chart pattern detection. */
    suspend fun chartPatterns(id: String, timeframe: Timeframe): ApiResult<List<ChartPattern>>

    /** Phase 9 — market structure analysis (HH/HL/LH/LL). */
    suspend fun marketStructure(id: String, timeframe: Timeframe, lookback: Int = 5): ApiResult<MarketStructure>

    /** Phase 3 endpoint, consumed from Phase 7 UI — OHLCV bars newest-last. */
    suspend fun candles(id: String, timeframe: Timeframe, limit: Int = 200): ApiResult<List<Candle>>

    /** TRADEBOT strict pattern engine (spec §35). Server scans its own stored
     *  timeframes; `timeframe` narrows the scan the way the endpoint defines it. */
    suspend fun patternSignals(
        id: String,
        timeframe: Timeframe? = null,
    ): ApiResult<List<TradePattern>>
}
