package com.bofedge.feature.instrument.chart

import android.annotation.SuppressLint
import android.webkit.WebView
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

/**
 * TradingView Advanced Chart Widget (official hosted). Clean chart — no pattern overlays.
 * Data source: TradingView's live feed for NSE instruments (NSE:SYMBOL format).
 *
 * Load: loadUrl("file:///android_asset/tradingview_widget.html?symbol=NSE:TCS&tf=1D")
 * The HTML reads ?symbol and ?tf from the URL, creates the widget via TV.js.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun TradingViewChartWebView(
    symbol: String = "NSE:RELIANCE",
    tf: String = "1D",
    modifier: Modifier = Modifier,
) {
    val url = "file:///android_asset/tradingview_widget.html?symbol=${symbol}&tf=${tf}"
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                settings.javaScriptEnabled = true
                settings.allowFileAccess = true
                setBackgroundColor(android.graphics.Color.parseColor("#0B0F14"))
                loadUrl(url)
            }
        },
        update = { web ->
            // Widget symbol is fixed at creation time (from URL);
            // reload only if symbol/timeframe changed by comparing current URL.
            val current = web.url ?: ""
            if (!current.contains(symbol) || !current.contains(tf)) {
                web.loadUrl("file:///android_asset/tradingview_widget.html?symbol=${symbol}&tf=${tf}")
            }
        },
    )
}
