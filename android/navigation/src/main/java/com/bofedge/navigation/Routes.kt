package com.bofedge.navigation

/**
 * Central route table. Root routing is auth-state driven (see AppRoot);
 * these routes cover in-shell destinations added across phases.
 */
object Routes {
    const val DASHBOARD = "dashboard"
    const val SCANNER = "scanner"
    const val HEATMAP = "heatmap"
    const val WATCHLIST = "watchlist"
    const val PROFILE = "profile"

    const val INSTRUMENT_DETAILS = "instrument/{instrumentId}"
    const val ARG_INSTRUMENT_ID = "instrumentId"

    fun instrumentDetails(instrumentId: String) = "instrument/$instrumentId"

    const val FULLSCREEN_CHART = "fullscreen/{instrumentId}/{symbol}"
    const val ARG_FS_SYMBOL = "symbol"

    fun fullscreenChart(instrumentId: String, symbol: String) =
        "fullscreen/$instrumentId/${android.net.Uri.encode(symbol)}"

    const val SETTINGS = "settings"
    const val NOTIFICATIONS = "notifications"
    const val ABOUT = "about"
}
