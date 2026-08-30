package com.bofedge.data.remote

import com.bofedge.data.remote.dto.ApiResponseDto
import com.bofedge.data.remote.dto.DashboardDto
import com.bofedge.data.remote.dto.FirebaseAuthRequestDto
import com.bofedge.data.remote.dto.InstrumentDetailDto
import com.bofedge.data.remote.dto.InstrumentDto
import com.bofedge.data.remote.dto.PageDto
import com.bofedge.data.remote.dto.UserDto
import com.bofedge.domain.model.Timeframe
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PATCH
import retrofit2.http.Path
import retrofit2.http.Query

interface BofApi {

    /** Exchange a Firebase ID token for the synchronized application user. */
    @POST("auth/firebase")
    suspend fun syncFirebaseUser(
        @Body body: FirebaseAuthRequestDto,
    ): ApiResponseDto<UserDto>

    /** Protected: returns the caller's profile from PostgreSQL. */
    @GET("profile")
    suspend fun getProfile(): ApiResponseDto<UserDto>

    // ------------------------------------------------------------- Phase 2

    @GET("dashboard")
    suspend fun dashboard(): ApiResponseDto<DashboardDto>

    @GET("instruments")
    suspend fun searchInstruments(
        @Query("q") query: String? = null,
        @Query("type") type: String? = null,
        @Query("sort") sort: String = "symbol",
        @Query("limit") limit: Int = 25,
        @Query("offset") offset: Int = 0,
    ): ApiResponseDto<PageDto<InstrumentDto>>

    @GET("instruments/{id}")
    suspend fun instrumentDetail(@Path("id") id: String): ApiResponseDto<InstrumentDetailDto>

    // ------------------------------------------------------------- Phase 5

    @GET("heatmap")
    suspend fun heatmap(
        @Query("group_by") groupBy: String = "sector",
        @Query("type") type: String? = null,
        @Query("only_with_signals") onlyWithSignals: Boolean = false,
    ): ApiResponseDto<com.bofedge.data.remote.dto.HeatmapResponseDto>

    @GET("instruments/{id}/signal-stats")
    suspend fun signalStats(@Path("id") id: String): ApiResponseDto<com.bofedge.data.remote.dto.SignalStatsDetailedDto>

    @GET("instruments/{id}/candles")
    suspend fun candles(
        @Path("id") id: String,
        @Query("timeframe") timeframe: Timeframe = Timeframe.DAILY,
        @Query("limit") limit: Int = 200,
    ): ApiResponseDto<com.bofedge.data.remote.dto.PaginatedCandlesDto>

    /** TRADEBOT strict pattern engine (spec §35). `timeframe` optional; when
     *  omitted the server scans its default (4H/1D) set. */
    @GET("instruments/{id}/patterns")
    suspend fun instrumentPatterns(
        @Path("id") id: String,
        @Query("timeframe") timeframe: String? = null,
    ): ApiResponseDto<com.bofedge.data.remote.dto.InstrumentPatternsDto>

    @GET("watchlists")
    suspend fun watchlists(): ApiResponseDto<List<com.bofedge.data.remote.dto.WatchlistDto>>

    @POST("watchlists")
    suspend fun createWatchlist(
        @Body body: com.bofedge.data.remote.dto.CreateWatchlistRequestDto,
    ): ApiResponseDto<com.bofedge.data.remote.dto.WatchlistDto>

    @PATCH("watchlists/{id}")
    suspend fun renameWatchlist(
        @Path("id") id: String,
        @Body body: com.bofedge.data.remote.dto.RenameWatchlistRequestDto,
    ): ApiResponseDto<com.bofedge.data.remote.dto.WatchlistDto>

    @DELETE("watchlists/{id}")
    suspend fun deleteWatchlist(@Path("id") id: String): ApiResponseDto<Map<String, Boolean>>

    @POST("watchlists/{id}/items")
    suspend fun addWatchlistItem(
        @Path("id") id: String,
        @Body body: com.bofedge.data.remote.dto.AddWatchlistItemRequestDto,
    ): ApiResponseDto<com.bofedge.data.remote.dto.WatchlistDto>

    @DELETE("watchlists/{id}/items/{instrumentId}")
    suspend fun removeWatchlistItem(
        @Path("id") id: String,
        @Path("instrumentId") instrumentId: String,
    ): ApiResponseDto<Map<String, Boolean>>

    @PATCH("watchlists/{id}/items/{instrumentId}")
    suspend fun updateWatchlistItem(
        @Path("id") id: String,
        @Path("instrumentId") instrumentId: String,
        @Body body: com.bofedge.data.remote.dto.UpdateWatchlistItemRequestDto,
    ): ApiResponseDto<com.bofedge.data.remote.dto.WatchlistDto>

    // ------------------------------------------------------------- Phase 6

    @POST("notifications/tokens")
    suspend fun registerNotificationToken(
        @Body body: com.bofedge.data.remote.dto.TokenRegisterRequestDto,
    ): ApiResponseDto<com.bofedge.data.remote.dto.TokenItemDto>

    @DELETE("notifications/tokens")
    suspend fun deactivateNotificationToken(
        @Query("fcm_token") fcmToken: String,
    ): ApiResponseDto<Map<String, Boolean>>

    @GET("notifications/preferences")
    suspend fun notificationPreferences(): ApiResponseDto<com.bofedge.data.remote.dto.PreferencesDto>

    @PATCH("notifications/preferences")
    suspend fun updateNotificationPreferences(
        @Body body: com.bofedge.data.remote.dto.PreferencesUpdateRequestDto,
    ): ApiResponseDto<com.bofedge.data.remote.dto.PreferencesDto>

    @GET("notifications")
    suspend fun notificationsOverview(): ApiResponseDto<com.bofedge.data.remote.dto.NotificationsOverviewDto>
}

