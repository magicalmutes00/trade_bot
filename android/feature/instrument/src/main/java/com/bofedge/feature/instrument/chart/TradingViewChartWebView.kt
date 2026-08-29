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
 * asset (offline-safe). Candle + indicator + pattern data crosses the bridge
 * as a JSON payload whenever inputs change; all indicator/pattern math lives in JS.
 * 
 * Architecture:
 * Kotlin  →  JSON serialization  →  WebView  →  Lightweight Charts JS  →  Render
 * 
 * Bridge carries: candles, sma20/ema9/bb/rsi, detected patterns, markers, timeframe, symbol
 * JavaScript → Kotlin: chart ready, crosshair changes, visible range changes (optional)
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun TradingViewChartWebView(
    candles: List<Candle>,
    timeframe: String = "1D",
    symbol: String = "",
    showSma20: Boolean = false,
    showEma9: Boolean = false,
    showBb: Boolean = false,
    showRsi: Boolean = false,
    indicators: List<String> = emptyList(),
    patternNames: List<String> = emptyList(),
    markers: List<Map<String, Any>> = emptyList(),
    modifier: Modifier = Modifier,
) {
    val payload = remember(candles, timeframe, symbol, showSma20, showEma9, showBb, showRsi, indicators, patternNames, markers) {
        buildPayload(candles, timeframe, symbol, showSma20, showEma9, showBb, showRsi, indicators, patternNames, markers)
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

/** Build the full JSON payload for the TradingView Lightweight Charts bridge.
 *  All indicator/pattern math lives in the JS layer; this payload is the
 *  serialized form of Kotlin-side data that JS consumes.
 */
private fun buildPayload(
    candles: List<Candle>,
    timeframe: String,
    symbol: String,
    sma20: Boolean,
    ema9: Boolean,
    bb: Boolean,
    rsi: Boolean,
    indicators: List<String>,
    patternNames: List<String>,
    markers: List<Map<String, Any>>,
): String {
    // 1. Candle data (newest-first DB order → oldest-first for LWC)
    val candleArr = JSONArray()
    for (c in candles.asReversed()) {
        val obj = JSONObject()
        obj.put("time", c.timeMillis / 1000L)
        obj.put("open", c.open)
        obj.put("high", c.high)
        obj.put("low", c.low)
        obj.put("close", c.close)
        obj.put("volume", c.volume)
        candleArr.put(obj)
    }

    // 2. Indicator values (SMA, EMA, BB, RSI) - passed as boolean flags;
    // actual values computed in JS
    val indicatorFlags = JSONObject().apply {
        put("sma20", sma20)
        put("ema9", ema9)
        put("bb", bb)
        put("rsi", rsi)
    }

    // 3. Detected patterns from Kotlin engine (names only; JS can recompute or use as reference)
    val patternsArr = JSONArray()
    patternNames.forEach { patternsArr.put(it) }

    // 4. Markers (price levels, pattern start/end points, etc.)
    val markersArr = JSONArray()
    markers.forEach { marker ->
        val mObj = JSONObject()
        marker.keys.asSequence().forEach { key ->
            val value = marker[key]
            when (value) {
                is Long -> mObj.put(key, value)
                is Double -> mObj.put(key, value)
                is String -> mObj.put(key, value)
                is Boolean -> mObj.put(key, value)
                else -> mObj.put(key, value.toString())
            }
        }
        markersArr.put(mObj)
    }

    // 5. Full payload object
    return JSONObject().apply {
        put("candles", candleArr)
        put("timeframe", timeframe)
        put("symbol", symbol)
        put("indicators", indicatorFlags)
        put("patterns", patternsArr)
        put("markers", markersArr)
        put("version", "lwc-android-bridge-1.0")
    }.toString()
}