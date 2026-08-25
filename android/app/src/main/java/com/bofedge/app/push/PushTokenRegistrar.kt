package com.bofedge.app.push

import com.bofedge.domain.repository.NotificationRepository
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.messaging.FirebaseMessaging
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.tasks.await

/**
 * Fetches the current FCM token and registers it against the signed-in user.
 * Silent by design — push setup must never break app startup.
 */
@Singleton
class PushTokenRegistrar @Inject constructor(
    private val notificationRepository: NotificationRepository,
    private val firebaseAuth: FirebaseAuth?,
) {
    suspend fun registerCurrent(deviceId: String? = null): Boolean {
        if (firebaseAuth?.currentUser == null) {
            return false // not signed in yet
        }
        return try {
            val token = FirebaseMessaging.getInstance().token.await()
            val result = notificationRepository.registerToken(
                fcmToken = token, deviceId = deviceId,
            )
            result is com.bofedge.domain.result.ApiResult.Success
        } catch (_: Exception) {
            false // offline / no Firebase config — retried on next app start
        }
    }
}
