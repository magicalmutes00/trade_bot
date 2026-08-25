package com.bofedge.data.repository

import com.bofedge.data.remote.BofApi
import com.bofedge.data.remote.dto.PreferencesUpdateRequestDto
import com.bofedge.data.remote.dto.TokenRegisterRequestDto
import com.bofedge.domain.model.DeviceTokenInfo
import com.bofedge.domain.model.NotificationPreferences
import com.bofedge.domain.repository.NotificationRepository
import com.bofedge.domain.result.ApiResult
import java.io.IOException
import javax.inject.Inject

class NotificationRepositoryImpl @Inject constructor(
    private val api: BofApi,
) : NotificationRepository {

    override suspend fun registerToken(
        fcmToken: String,
        platform: String,
        deviceId: String?,
    ): ApiResult<DeviceTokenInfo> = guarded {
        val t = requireData(api.registerNotificationToken(
            TokenRegisterRequestDto(fcmToken = fcmToken, platform = platform, deviceId = deviceId)
        ))
        DeviceTokenInfo(id = t.id, platform = t.platform, isActive = t.isActive)
    }

    override suspend fun deactivateToken(fcmToken: String): ApiResult<Unit> = guarded {
        api.deactivateNotificationToken(fcmToken)
        Unit
    }

    override suspend fun preferences(): ApiResult<NotificationPreferences> = guarded {
        val p = requireData(api.notificationPreferences())
        p.toDomain()
    }

    override suspend fun updatePreferences(
        pushEnabled: Boolean?, bullishAlerts: Boolean?, bearishAlerts: Boolean?,
        strongOnly: Boolean?, watchlistOnly: Boolean?, minStrength: String?,
    ): ApiResult<NotificationPreferences> = guarded {
        val p = requireData(api.updateNotificationPreferences(
            PreferencesUpdateRequestDto(
                pushEnabled = pushEnabled,
                bullishAlerts = bullishAlerts,
                bearishAlerts = bearishAlerts,
                strongOnly = strongOnly,
                watchlistOnly = watchlistOnly,
                minStrength = minStrength,
            )
        ))
        p.toDomain()
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

    private fun <T> requireData(body: com.bofedge.data.remote.dto.ApiResponseDto<T>): T =
        body.data ?: throw HttpEnvelopeException(
            code = body.error?.code ?: "UNKNOWN",
            message = body.error?.message ?: "Unexpected server response",
        )

    private fun com.bofedge.data.remote.dto.PreferencesDto.toDomain() =
        NotificationPreferences(
            pushEnabled = pushEnabled,
            bullishAlerts = bullishAlerts,
            bearishAlerts = bearishAlerts,
            strongOnly = strongOnly,
            watchlistOnly = watchlistOnly,
            minStrength = minStrength,
        )
}
