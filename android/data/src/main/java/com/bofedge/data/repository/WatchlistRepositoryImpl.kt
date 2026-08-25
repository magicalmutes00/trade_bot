package com.bofedge.data.repository

import com.bofedge.data.remote.BofApi
import com.bofedge.data.remote.dto.AddWatchlistItemRequestDto
import com.bofedge.data.remote.dto.CreateWatchlistRequestDto
import com.bofedge.data.remote.dto.RenameWatchlistRequestDto
import com.bofedge.data.remote.dto.UpdateWatchlistItemRequestDto
import com.bofedge.data.remote.dto.WatchlistDto
import com.bofedge.domain.model.Watchlist
import com.bofedge.domain.model.WatchlistEntry
import com.bofedge.domain.repository.WatchlistRepository
import com.bofedge.domain.result.ApiResult
import java.io.IOException
import javax.inject.Inject

class WatchlistRepositoryImpl @Inject constructor(
    private val api: BofApi,
) : WatchlistRepository {

    override suspend fun list(): ApiResult<List<Watchlist>> = guarded {
        (api.watchlists().data ?: emptyList()).map { it.toDomain() }
    }

    override suspend fun create(name: String): ApiResult<Watchlist> = guarded {
        (api.createWatchlist(CreateWatchlistRequestDto(name)).data
            ?: throw HttpEnvelopeException("UNKNOWN", "no data")).toDomain()
    }

    override suspend fun rename(id: String, newName: String): ApiResult<Watchlist> = guarded {
        (api.renameWatchlist(id, RenameWatchlistRequestDto(newName)).data
            ?: throw HttpEnvelopeException("UNKNOWN", "no data")).toDomain()
    }

    override suspend fun delete(id: String): ApiResult<Unit> = guarded {
        api.deleteWatchlist(id)
        Unit
    }

    override suspend fun addItem(watchlistId: String, instrumentId: String,
                                 alertEnabled: Boolean): ApiResult<Watchlist> = guarded {
        (api.addWatchlistItem(watchlistId, AddWatchlistItemRequestDto(instrumentId, alertEnabled)).data
            ?: throw HttpEnvelopeException("UNKNOWN", "no data")).toDomain()
    }

    override suspend fun removeItem(watchlistId: String, instrumentId: String): ApiResult<Unit> = guarded {
        api.removeWatchlistItem(watchlistId, instrumentId)
        Unit
    }

    override suspend fun setAlert(watchlistId: String, instrumentId: String,
                                  enabled: Boolean): ApiResult<Watchlist> = guarded {
        (api.updateWatchlistItem(watchlistId, instrumentId,
            UpdateWatchlistItemRequestDto(alertEnabled = enabled)).data
            ?: throw HttpEnvelopeException("UNKNOWN", "no data")).toDomain()
    }

    private inline fun <T> guarded(block: () -> T): ApiResult<T> = try {
        ApiResult.Success(block())
    } catch (e: HttpEnvelopeException) {
        ApiResult.HttpError(code = e.code, message = e.message)
    } catch (e: IOException) {
        ApiResult.Offline
    } catch (e: retrofit2.HttpException) {
        ApiResult.HttpError(code = "HTTP_${e.code()}", message = e.message(), httpStatus = e.code())
    }

    private fun WatchlistDto.toDomain() = Watchlist(
        id = id,
        name = name,
        entries = items.map { item ->
            WatchlistEntry(
                instrumentId = item.instrumentId,
                symbol = item.symbol,
                name = item.name,
                type = item.type,
                sectorName = item.sectorName,
                position = item.position,
                alertEnabled = item.alertEnabled,
                lastPrice = item.lastPrice,
                changePct = item.changePct,
                bofDirection = item.bofDirection,
                bofStrength = item.bofStrength,
                bofStatus = item.bofStatus,
            )
        },
    )
}
