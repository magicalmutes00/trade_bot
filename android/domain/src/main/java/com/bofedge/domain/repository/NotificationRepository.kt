package com.bofedge.domain.repository

import com.bofedge.domain.model.DeviceTokenInfo
import com.bofedge.domain.model.NotificationPreferences
import com.bofedge.domain.result.ApiResult

interface NotificationRepository {
    /** Registers/refreshes this device's FCM token against the signed-in user. */
    suspend fun registerToken(
        fcmToken: String,
        platform: String = "ANDROID",
        deviceId: String? = null,
    ): ApiResult<DeviceTokenInfo>

    suspend fun deactivateToken(fcmToken: String): ApiResult<Unit>

    suspend fun preferences(): ApiResult<NotificationPreferences>

    suspend fun updatePreferences(
        pushEnabled: Boolean? = null,
        bullishAlerts: Boolean? = null,
        bearishAlerts: Boolean? = null,
        strongOnly: Boolean? = null,
        watchlistOnly: Boolean? = null,
        minStrength: String? = null,
    ): ApiResult<NotificationPreferences>
}
