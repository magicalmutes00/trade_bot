package com.bofedge.app.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.bofedge.app.R
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

private const val CHANNEL_ID = "bof_signals"

/**
 * Renders data-only pushes from /ws pipeline fan-out as system notifications
 * and keeps the backend's FCM token fresh when Firebase rotates it.
 */
@AndroidEntryPoint
class BofMessagingService : FirebaseMessagingService() {

    @Inject lateinit var tokenRegistrar: PushTokenRegistrar

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        scope.launch { tokenRegistrar.registerCurrent() }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val type = data["type"] ?: return
        if (type != "bof_signal" && type != "market_status" && type != "test") return

        val title = message.notification?.title
            ?: data["symbol"]?.let { "BOF $type — $it" }
            ?: getString(R.string.app_name)
        val body = message.notification?.body ?: ""

        showNotification(title, body)
    }

    private fun showNotification(title: String, body: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "TradeBot signals",
                    NotificationManager.IMPORTANCE_DEFAULT).apply {
                    description = "Breakout failure alerts"
                },
            )
        }
        val intent = packageManager.getLaunchIntentForPackage(packageName)
        val pending = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_bof_edge)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()
        manager.notify(body.hashCode(), notification)
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
