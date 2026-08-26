package com.bofedge.feature.instrument.chart

import android.annotation.SuppressLint
import android.webkit.WebView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.bofedge.domain.model.Candle
import org.json.JSONArray
import org.json.JSONObject

/**
 * TradingView lightweight-charts rendered in a WebView over a bundled local
 * asset (offline-safe). Candle + indicator data crosses the bridge as one
 * JSON payload whenever the inputs change; all indicator math lives in JS.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun TradingViewChartWebView(
    candles: List<Candle>,
    showSma20: Boolean,
    showEma9: Boolean,
    showBb: Boolean,
    showRsi: Boolean,
    modifier: Modifier = Modifier,
) {
    val payload = remember(candles, showSma20, showEma9, showBb, showRsi) {
        buildPayload(candles, showSma20, showEma9, showBb, showRsi)
    }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                settings.javaScriptEnabled = true
                settings.allowFileAccess = true
                setBackgroundColor(android.graphics.Color.parseColor("#0B0F14"))
                loadUrl("file:///android_asset/chart.html")
            }
        },
        update = { web ->
            web.evaluateJavascript("window.updateChart($payload)", null)
        },
    )
}

private fun buildPayload(
    candles: List<Candle>,
    sma20: Boolean, ema9: Boolean, bb: Boolean, rsi: Boolean,
): String {
    val arr = JSONArray()
    for (c in candles.asReversed()) {           // newest-first DB order → oldest-first for LWC
        arr.put(
            JSONObject()
                .put("time", c.timeMillis / 1000L)
                .put("open", c.open)
                .put("high", c.high)
                .put("low", c.low)
                .put("close", c.close)
                .put("volume", c.volume),
        )
    }
    return JSONObject()
        .put("candles", arr)
        .put("sma20", sma20)
        .put("ema9", ema9)
        .put("bb", bb)
        .put("rsi", rsi)
        .toString()
}
