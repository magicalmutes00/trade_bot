package com.bofedge.data.network

import com.bofedge.data.remote.dto.QuoteTickDto
import com.bofedge.domain.model.QuoteTick
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton
import kotlin.coroutines.cancellation.CancellationException

/** Events surfaced to the UI layer. */
sealed class WsEvent {
    data object Connecting : WsEvent()
    data object Live : WsEvent()
    data class Reconnecting(val delayMs: Long) : WsEvent()
    data class Quotes(val ticks: List<QuoteTick>) : WsEvent()
}

/**
 * OkHttp WebSocket with automatic exponential-backoff reconnection.
 *
 * - One shared instance; [connect]/[disconnect] control the desired state.
 * - Every transition arrives on [events] (SharedFlow, replay=1).
 * - Tokens are never part of the socket URL/payload (public market feed).
 */
@Singleton
class MarketSocketClient @Inject constructor(
    private val okHttpClient: OkHttpClient,
    private val json: Json,
    @Named("wsUrl") private val url: String,
) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _events = kotlinx.coroutines.flow.MutableSharedFlow<WsEvent>(
        replay = 1,
        onBufferOverflow = kotlinx.coroutines.channels.BufferOverflow.DROP_OLDEST,
    )
    val events: kotlinx.coroutines.flow.SharedFlow<WsEvent> = _events

    private var webSocket: WebSocket? = null
    private var attempts = 0
    private var wantConnected = false

    fun connect() {
        if (wantConnected) return
        wantConnected = true
        attempts = 0
        open()
    }

    fun disconnect() {
        wantConnected = false
        webSocket?.close(1001, "client going away")
        webSocket = null
    }

    fun shutdown() {
        scope.cancel()
    }

    private fun open() {
        _events.tryEmit(WsEvent.Connecting)
        val request = Request.Builder().url(url).build()
        webSocket = okHttpClient.newWebSocket(request, Listener())
    }

    private fun scheduleReconnect() {
        if (!wantConnected) return
        val delayMs = ReconnectBackoff.delayMillis(attempts++)
        _events.tryEmit(WsEvent.Reconnecting(delayMs))
        scope.launch {
            try {
                kotlinx.coroutines.delay(delayMs)
                if (wantConnected) open()
            } catch (_: CancellationException) {
                // shutting down
            }
        }
    }

    private fun emitQuotes(text: String) {
        val payload = runCatching { extractDataArray(text) }.getOrNull() ?: return
        val serializer: kotlinx.serialization.KSerializer<List<QuoteTickDto>> =
            kotlinx.serialization.builtins.ListSerializer(QuoteTickDto.serializer())
        runCatching {
            val parsed = json.decodeFromString(serializer, payload)
            _events.tryEmit(
                WsEvent.Quotes(
                    parsed.map { QuoteTick(it.symbol, it.lastPrice, it.changePct, it.direction, it.ts) }
                )
            )
        }
    }

    /** `{"type":"quotes","data":[ … ]}` → `[ … ]` */
    internal fun extractDataArray(text: String): String {
        val marker = "\"data\":"
        val idx = text.indexOf(marker)
        require(idx >= 0) { "no data field" }
        return text.substring(idx + marker.length).trimEnd('}', '\n', ' ', '\t')
    }

    inner class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            attempts = 0
            _events.tryEmit(WsEvent.Live)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (text.contains("\"type\":\"quotes\"")) {
                emitQuotes(text)
            }
            // hello / pong / signals / market_status handled by later phases of UI wiring
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            scheduleReconnect()
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            scheduleReconnect()
        }
    }
}
