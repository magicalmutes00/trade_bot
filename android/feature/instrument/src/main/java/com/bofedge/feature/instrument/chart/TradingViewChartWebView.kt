package com.bofedge.feature.instrument.chart

import android.annotation.SuppressLint
import android.util.Log
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.webkit.WebViewAssetLoader
import com.bofedge.domain.model.Candle
import org.json.JSONArray
import org.json.JSONObject

private const val TAG = "TVChart"

/**
 * Local TradingView Lightweight Charts bundle (already in assets/), served via
 * WebViewAssetLoader at https://appassets.androidplatform.net/ so the WebView
 * has a real https origin (file:// is opaque; remote DataUploader calls fail).
 *
 * Pure offline chart: no TradingView server, no symbol feed. Candles come from
 * the backend (InstrumentRepository.candles). LWC draws them locally.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun TradingViewChartWebView(
    candles: List<Candle>,
    timeframe: String = "1D",
    symbol: String = "",
    patternNames: List<String> = emptyList(),
    markers: List<Map<String, Any>> = emptyList(),
    quotePrice: Double? = null,
    quotePct: Double? = null,
    modifier: Modifier = Modifier,
) {
    val payload = remember(candles, timeframe, symbol, patternNames, markers, quotePrice, quotePct) {
        buildPayload(candles, timeframe, symbol, patternNames, markers, quotePrice, quotePct)
    }
    val url = "https://appassets.androidplatform.net/assets/tradingview_widget.html"

    // pageReady flips true inside onPageFinished. The update lambda waits for it
    // so the first payload isn't lost racing the page load.
    var pageReady by remember { mutableStateOf(false) }
    var webView by remember { mutableStateOf<WebView?>(null) }

    Log.d(TAG, "init candles=${candles.size} tf=$timeframe symbol=$symbol payloadBytes=${payload.length}")

    // Re-feed payload whenever data changes and page is loaded.
    // We call evaluateJavascript with the payload embedded as a JSON literal.
    LaunchedEffect(payload, pageReady, webView) {
        val w = webView
        if (pageReady && w != null) {
            // Escape payload for JS: wrap in single-quoted JSON, with internal quotes escaped.
            val escaped = payload.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r")
            Log.d(TAG, "LaunchedEffect feeding payload (candles=${candles.size}) payloadLen=${payload.length}")
            w.evaluateJavascript("window.updateChart(\"$escaped\");", null)
        }
    }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                Log.d(TAG, "factory WebView created")
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.loadWithOverviewMode = true
                settings.useWideViewPort = true
                settings.allowFileAccess = false
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                setBackgroundColor(android.graphics.Color.parseColor("#0B0F14"))

                val assetLoader = WebViewAssetLoader.Builder()
                    .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(ctx))
                    .build()

                webChromeClient = object : android.webkit.WebChromeClient() {
                    override fun onConsoleMessage(consoleMessage: android.webkit.ConsoleMessage): Boolean {
                        val lvl = consoleMessage.messageLevel()
                        val msg = "[TV JS] ${consoleMessage.message()} (line:${consoleMessage.lineNumber()})"
                        if (lvl == android.webkit.ConsoleMessage.MessageLevel.ERROR) Log.e(TAG, msg)
                        else Log.d(TAG, msg)
                        return true
                    }
                }

                webViewClient = object : WebViewClient() {
                    override fun shouldInterceptRequest(
                        view: WebView,
                        request: WebResourceRequest,
                    ) = assetLoader.shouldInterceptRequest(request.url)

                    override fun onPageFinished(view: WebView?, url: String?) {
                        Log.d(TAG, "pageFinished, marking ready")
                        pageReady = true
                    }

                    override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: android.webkit.WebResourceError?) {
                        Log.e(TAG, "onReceivedError url=${request?.url} code=${error?.errorCode} desc=${error?.description}")
                    }
                }
                loadUrl(url)
                webView = this
            }
        },
        // update kept empty: LaunchedEffect above does the work, gated on pageReady.
        update = { _ -> },
    )
}

private fun buildPayload(
    candles: List<Candle>,
    timeframe: String,
    symbol: String,
    patternNames: List<String>,
    markers: List<Map<String, Any>>,
    quotePrice: Double? = null,
    quotePct: Double? = null,
): String {
    val candleArr = JSONArray()
    for (c in candles) {
        val obj = JSONObject()
        obj.put("time", c.timeMillis / 1000L)
        obj.put("open", c.open)
        obj.put("high", c.high)
        obj.put("low", c.low)
        obj.put("close", c.close)
        obj.put("volume", c.volume)
        candleArr.put(obj)
    }
    val markersArr = JSONArray()
    for (marker in markers) {
        val mObj = JSONObject()
        for (key in marker.keys) {
            val v = marker[key]
            when (v) {
                is Long -> mObj.put(key, v)
                is Double -> mObj.put(key, v)
                is String -> mObj.put(key, v)
                is Boolean -> mObj.put(key, v)
                else -> mObj.put(key, v.toString())
            }
        }
        markersArr.put(mObj)
    }
    val payloadObj = JSONObject().apply {
        put("candles", candleArr)
        put("timeframe", timeframe)
        put("symbol", symbol)
        put("patterns", JSONArray(patternNames))
        put("markers", markersArr)
        if (quotePrice != null || quotePct != null) {
            val quoteObj = JSONObject()
            if (quotePrice != null) quoteObj.put("lastPrice", quotePrice)
            if (quotePct != null) quoteObj.put("changePct", quotePct)
            put("quote", quoteObj)
        }
    }
    return payloadObj.toString()
}
