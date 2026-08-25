package com.bofedge.domain.model

/** Live quote tick streamed over /ws/market (demo provider marked isDemo). */
data class QuoteTick(
    val symbol: String,
    val lastPrice: Double,
    val changePct: Double?,
    val direction: String?,
    val ts: String?,
)

/** Realtime connection state exposed to the UI. */
enum class RealtimeConnection { CONNECTING, LIVE, RECONNECTING, OFFLINE }
