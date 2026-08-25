package com.bofedge.domain.model

data class NotificationPreferences(
    val pushEnabled: Boolean,
    val bullishAlerts: Boolean,
    val bearishAlerts: Boolean,
    val strongOnly: Boolean,
    val watchlistOnly: Boolean,
    val minStrength: String,
)

data class DeviceTokenInfo(
    val id: String,
    val platform: String,
    val isActive: Boolean,
)
