package com.bofedge.data.repository

import com.bofedge.data.remote.BofApi
import com.bofedge.data.remote.dto.InstrumentDetailDto
import com.bofedge.data.remote.dto.InstrumentDto
import com.bofedge.domain.model.BofSummary
import com.bofedge.domain.model.DashboardSnapshot
import com.bofedge.domain.model.HeatmapCell
import com.bofedge.domain.model.HeatmapGroup
import com.bofedge.domain.model.IndexQuote
import com.bofedge.domain.model.Instrument
import com.bofedge.domain.model.InstrumentDetail
import com.bofedge.domain.model.InstrumentQuote
import com.bofedge.domain.model.MarketStatusInfo
import com.bofedge.domain.model.PageResult
import com.bofedge.domain.model.SignalCard
import com.bofedge.domain.model.SignalStats
import com.bofedge.domain.model.SignalStatsDetailed
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.repository.InstrumentSort
import com.bofedge.domain.result.ApiResult
import java.io.IOException
import javax.inject.Inject

class InstrumentRepositoryImpl @Inject constructor(
    private val api: BofApi,
) : InstrumentRepository {

    override suspend fun search(
        query: String?,
        type: String?,
        sort: InstrumentSort,
        limit: Int,
        offset: Int,
    ): ApiResult<PageResult<Instrument>> = guarded {
        val body = api.searchInstruments(
            query = query?.takeIf { it.isNotBlank() },
            type = type,
            sort = sort.wire,
            limit = limit,
            offset = offset,
        )
        val page = requireData(body)
        PageResult(items = page.items.map { it.toDomain() }, total = page.total, offset = page.offset)
    }

    override suspend fun detail(id: String): ApiResult<InstrumentDetail> = guarded {
        requireData(api.instrumentDetail(id)).toDomain()
    }

    override suspend fun dashboard(): ApiResult<DashboardSnapshot> = guarded {
        val d = requireData(api.dashboard())
        DashboardSnapshot(
            marketStatus = MarketStatusInfo(d.marketStatus.market, d.marketStatus.status),
            bofSummary = BofSummary(
                activeTotal = d.bofSummary.activeTotal,
                bullish = d.bofSummary.bullish,
                bearish = d.bofSummary.bearish,
                strong = d.bofSummary.strong,
                newToday = d.bofSummary.newToday,
                detectedToday = d.bofSummary.detectedToday,
            ),
            indices = d.indices.map {
                IndexQuote(it.instrumentId, it.symbol, it.name, it.lastPrice, it.changePct, it.direction)
            },
            latestSignals = d.latestSignals.map { it.toCard() },
            strongestSignals = d.strongestSignals.map { it.toCard() },
        )
    }

    override suspend fun heatmap(
        groupBy: String,
        type: String?,
        onlyWithSignals: Boolean,
    ): ApiResult<List<HeatmapGroup>> = guarded {
        val data = requireData(api.heatmap(groupBy, type, onlyWithSignals))
        data.groups.map { g ->
            HeatmapGroup(
                key = g.key,
                label = g.label,
                cells = g.cells.map { c ->
                    HeatmapCell(
                        instrumentId = c.instrumentId,
                        symbol = c.symbol,
                        name = c.name,
                        type = c.type,
                        sectorName = c.sectorName,
                        lastPrice = c.lastPrice,
                        changePct = c.changePct,
                        bofDirection = c.bofDirection,
                        bofStrength = c.bofStrength,
                        bofStatus = c.bofStatus,
                    )
                },
            )
        }
    }

    override suspend fun signalStats(id: String): ApiResult<SignalStatsDetailed> = guarded {
        val s = requireData(api.signalStats(id))
        SignalStatsDetailed(
            totalSignals = s.totalSignals,
            bullish = s.bullish,
            bearish = s.bearish,
            confirmed = s.confirmed,
            invalidated = s.invalidated,
            detecting = s.detecting,
            avgConfidence = s.avgConfidence,
            confirmationRate = s.confirmationRate,
        )
    }

    // ------------------------------------------------------------------ utils

    private inline fun <T> guarded(block: () -> T): ApiResult<T> = try {
        ApiResult.Success(block())
    } catch (e: HttpEnvelopeException) {
        ApiResult.HttpError(code = e.code, message = e.message)
    } catch (e: IOException) {
        ApiResult.Offline
    } catch (e: retrofit2.HttpException) {
        ApiResult.HttpError(code = "HTTP_${e.code()}", message = e.message(), httpStatus = e.code())
    }

    /** Throws the typed envelope failure unless success && data != null. */
    private fun <T> requireData(body: com.bofedge.data.remote.dto.ApiResponseDto<T>): T {
        val data = body.data
        if (!body.success || data == null) {
            throw HttpEnvelopeException(
                code = body.error?.code ?: "UNKNOWN",
                message = body.error?.message ?: "Unexpected server response",
            )
        }
        return data
    }

    private fun com.bofedge.data.remote.dto.SignalCardDto.toCard() =
        SignalCard(
            id = id, instrumentId = instrumentId, symbol = symbol,
            direction = direction, strength = strength, status = status,
            bofLevel = bofLevel, confidence = confidence,
            timeframe = timeframe, detectedAt = detectedAt ?: "",
        )

    private fun InstrumentDto.toDomain() = Instrument(
        id = id, symbol = symbol, name = name, type = type,
        exchange = exchange, currency = currency, sectorName = sectorName,
    )

    private fun InstrumentDetailDto.toDomain() = InstrumentDetail(
        id = id, symbol = symbol, name = name, type = type,
        exchange = exchange, currency = currency, sectorName = sectorName,
        tickSize = tickSize?.toDoubleOrNull(),
        lotSize = lotSize,
        quote = quote?.let {
            InstrumentQuote(
                lastPrice = it.lastPrice?.toDoubleOrNull(),
                change = it.change?.toDoubleOrNull(),
                changePct = it.changePct?.toDoubleOrNull(),
                volume = it.volume,
                updatedAt = it.updatedAt,
            )
        },
        stats = SignalStats(
            totalSignals = stats.totalSignals,
            bullish = stats.bullish,
            bearish = stats.bearish,
            confirmed = stats.confirmed,
            invalidated = stats.invalidated,
        ),
    )
}

/** Raised inside [guarded] when the server returns a well-formed error envelope. */
class HttpEnvelopeException(val code: String, override val message: String) : RuntimeException(message)


