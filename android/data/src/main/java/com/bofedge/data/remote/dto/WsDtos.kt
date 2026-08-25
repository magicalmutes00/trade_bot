package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Envelopes pushed by /ws/market: {"type": "...", "data": {...}} */

@Serializable
data class WsHelloDto(
    @SerialName("server_time") val serverTime: String? = null,
    @SerialName("tick_interval_seconds") val tickIntervalSeconds: Int? = null,
    @SerialName("provider") val provider: String? = null,
)

@Serializable
data class QuoteTickDto(
    @SerialName("symbol") val symbol: String,
    @SerialName("last_price") val lastPrice: Double = 0.0,
    @SerialName("change_pct") val changePct: Double? = null,
    @SerialName("direction") val direction: String? = null,
    @SerialName("is_demo") val isDemo: Boolean = true,
    @SerialName("ts") val ts: String? = null,
)

@Serializable
data class MarketStatusUpdateDto(
    @SerialName("market") val market: String = "NSE",
    @SerialName("status") val status: String = "CLOSED",
)
