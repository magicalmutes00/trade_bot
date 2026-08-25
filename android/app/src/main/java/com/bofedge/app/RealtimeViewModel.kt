package com.bofedge.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.data.network.MarketSocketClient
import com.bofedge.data.network.WsEvent
import com.bofedge.domain.model.QuoteTick
import com.bofedge.domain.model.RealtimeConnection
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class RealtimeUiState(
    val connection: RealtimeConnection = RealtimeConnection.CONNECTING,
    val ticks: Map<String, QuoteTick> = emptyMap(),
    val reconnectInMs: Long? = null,
)

/**
 * Owns the WebSocket lifecycle while the shell is authenticated and exposes a
 * snapshot the dashboard renders (live chip + top movers).
 */
@HiltViewModel
class RealtimeViewModel @Inject constructor(
    private val socket: MarketSocketClient,
    private val pushTokenRegistrar: com.bofedge.app.push.PushTokenRegistrar,
) : ViewModel() {

    private val _state = MutableStateFlow(RealtimeUiState())
    val state: StateFlow<RealtimeUiState> = _state.asStateFlow()

    init {
        socket.connect()
        registerPushToken()
        viewModelScope.launch {
            socket.events.collect { event ->
                when (event) {
                    WsEvent.Connecting -> _state.update {
                        it.copy(connection = RealtimeConnection.CONNECTING)
                    }
                    WsEvent.Live -> _state.update {
                        it.copy(connection = RealtimeConnection.LIVE, reconnectInMs = null)
                    }
                    is WsEvent.Reconnecting -> _state.update {
                        it.copy(
                            connection = RealtimeConnection.RECONNECTING,
                            reconnectInMs = event.delayMs,
                        )
                    }
                    is WsEvent.Quotes -> _state.update { s ->
                        val merged = s.ticks.toMutableMap()
                        event.ticks.forEach { tick -> merged[tick.symbol] = tick }
                        s.copy(ticks = merged, connection = RealtimeConnection.LIVE)
                    }
                }
            }
        }
    }

    /** Registers the FCM device token (Phase 6); silent on any failure. */
    private fun registerPushToken() {
        viewModelScope.launch {
            runCatching { pushTokenRegistrar.registerCurrent() }
        }
    }

    override fun onCleared() {
        socket.disconnect()
        super.onCleared()
    }
}
