package com.bofedge.feature.instrument.chart

import android.annotation.SuppressLint
import android.net.Uri
import android.webkit.WebView
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.webkit.WebViewAssetLoader

/**
 * TradingView Advanced Chart Widget (official hosted). Clean chart — no pattern overlays.
 * Data source: TradingView's live feed for NSE instruments (NSE:SYMBOL format).
 *
 * The HTML is served via WebViewAssetLoader at https://appassets.androidplatform.net/...
 * so the page gets a real https origin (file:// origin is opaque and blocks the widget
 * cross-origin fetches). The loader rewrites https://appassets.androidplatform.net/assets/...
 * to file:///android_asset/... and the page is loaded as https so tv.js can talk to TV servers.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun TradingViewChartWebView(
    symbol: String = "NSE:RELIANCE",
    tf: String = "1D",
    modifier: Modifier = Modifier,
) {
    val url = "https://appassets.androidplatform.net/assets/tradingview_widget.html" +
        "?symbol=${Uri.encode(symbol)}&tf=${Uri.encode(tf)}"
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.loadWithOverviewMode = true
                settings.useWideViewPort = true
                settings.setSupportZoom(true)
                settings.allowFileAccess = false
                // Mixed content (https page + http assets) — Android 9+ blocks by default.
                settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                setBackgroundColor(android.graphics.Color.parseColor("#0B0F14"))

                val assetLoader = WebViewAssetLoader.Builder()
                    .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(ctx))
                    .build()

                webViewClient = object : android.webkit.WebViewClient() {
                    override fun shouldInterceptRequest(
                        view: WebView,
                        request: android.webkit.WebResourceRequest,
                    ): android.webkit.WebResourceResponse? = assetLoader.shouldInterceptRequest(request.url)

                    override fun shouldOverrideUrlLoading(view: WebView, request: android.webkit.WebResourceRequest): Boolean {
                        // Allow navigation within our asset origin only; open external links in browser
                        val host = request.url.host
                        return if (host == "appassets.androidplatform.net") false
                        else true
                    }
                }
                loadUrl(url)
            }
        },
        update = { web ->
            val current = web.url ?: ""
            if (!current.contains(symbol) || !current.contains(tf)) {
                web.loadUrl(url)
            }
        },
    )
}
