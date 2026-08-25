package com.bofedge.domain.repository

import com.bofedge.domain.model.DashboardSnapshot
import com.bofedge.domain.model.HeatmapGroup
import com.bofedge.domain.model.Instrument
import com.bofedge.domain.model.InstrumentDetail
import com.bofedge.domain.model.PageResult
import com.bofedge.domain.model.SignalStatsDetailed
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
}
