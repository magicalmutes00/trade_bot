package com.bofedge.domain.repository

import com.bofedge.domain.model.Watchlist
import com.bofedge.domain.result.ApiResult

interface WatchlistRepository {
    suspend fun list(): ApiResult<List<Watchlist>>

    suspend fun create(name: String): ApiResult<Watchlist>

    suspend fun rename(id: String, newName: String): ApiResult<Watchlist>

    suspend fun delete(id: String): ApiResult<Unit>

    suspend fun addItem(watchlistId: String, instrumentId: String,
                        alertEnabled: Boolean = false): ApiResult<Watchlist>

    suspend fun removeItem(watchlistId: String, instrumentId: String): ApiResult<Unit>

    suspend fun setAlert(watchlistId: String, instrumentId: String,
                         enabled: Boolean): ApiResult<Watchlist>
}
