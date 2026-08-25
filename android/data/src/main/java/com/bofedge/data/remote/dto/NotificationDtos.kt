package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TokenRegisterRequestDto(
    @SerialName("fcm_token") val fcmToken: String,
    @SerialName("platform") val platform: String = "ANDROID",
    @SerialName("device_id") val deviceId: String? = null,
)

@Serializable
data class TokenItemDto(
    @SerialName("id") val id: String,
    @SerialName("platform") val platform: String = "ANDROID",
    @SerialName("device_id") val deviceId: String? = null,
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class PreferencesDto(
    @SerialName("push_enabled") val pushEnabled: Boolean = true,
    @SerialName("bullish_alerts") val bullishAlerts: Boolean = true,
    @SerialName("bearish_alerts") val bearishAlerts: Boolean = true,
    @SerialName("strong_only") val strongOnly: Boolean = false,
    @SerialName("watchlist_only") val watchlistOnly: Boolean = false,
    @SerialName("min_strength") val minStrength: String = "MODERATE",
)

@Serializable
data class PreferencesUpdateRequestDto(
    @SerialName("push_enabled") val pushEnabled: Boolean? = null,
    @SerialName("bullish_alerts") val bullishAlerts: Boolean? = null,
    @SerialName("bearish_alerts") val bearishAlerts: Boolean? = null,
    @SerialName("strong_only") val strongOnly: Boolean? = null,
    @SerialName("watchlist_only") val watchlistOnly: Boolean? = null,
    @SerialName("min_strength") val minStrength: String? = null,
)

@Serializable
data class NotificationsOverviewDto(
    @SerialName("preferences") val preferences: PreferencesDto = PreferencesDto(),
    @SerialName("tokens") val tokens: List<TokenItemDto> = emptyList(),
)
