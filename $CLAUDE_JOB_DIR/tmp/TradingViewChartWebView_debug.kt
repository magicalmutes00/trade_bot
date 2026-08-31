package com.bofedge.feature.instrument.chart

import android.annotation.SuppressLint
import android.net.Uri
import android.util.Log
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.webkit.WebViewAssetLoader

private const val TAG = "TVChart"

/**
 * TradingView Advanced Chart Widget (hosted, with logcat diagnostics).
 * If blank: check logcat for "TVChart" lines — will show load URL, intercept
 * result (asset loader hit/miss), page finish, JS errors, and WebView errors.
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
    Log.d(TAG, "init url=$url symbol=$symbol tf=$tf")
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                Log.d(TAG, "factory WebView created")
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.loadWithOverviewMode = true
                settings.useWideViewPort = true
                settings.setSupportZoom(true)
                settings.allowFileAccess = false
                settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                setBackgroundColor(android.graphics.Color.parseColor("#0B0F14"))

                val assetLoader = WebViewAssetLoader.Builder()
                    .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(ctx))
                    .build()

                webViewClient = object : WebViewClient() {
                    override fun shouldInterceptRequest(
                        view: WebView,
                        request: WebResourceRequest,
                    ): WebResourceResponse? {
                        val res = assetLoader.shouldInterceptRequest(request.url)
                        Log.d(TAG, "intercept url=${request.url} -> ${res != null}")
                        return res
                    }

                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                        val host = request.url.host ?: ""
                        Log.d(TAG, "navigate host=$host url=${request.url}")
                        return if (host == "appassets.androidplatform.net") false else true
                    }

                    override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                        Log.d(TAG, "pageStarted url=$url")
                        super.onPageStarted(view, url, favicon)
                    }

                    override fun onPageFinished(view: WebView?, url: String?) {
                        Log.d(TAG, "pageFinished url=$url")
                        // Inject debug message into body so user can see errors on screen
                        view?.evaluateJavascript(
                            "try { document.body.insertAdjacentHTML('beforeend', '<div id=\"tv-debug\" style=\"position:fixed;top:0;left:0;background:#c62828;color:#fff;padding:8px;font-family:monospace;font-size:12px;z-index:9999\">TV loaded OK — symbol=${symbol}</div>'); } catch(e){ console.error('debug inject fail', e); }"
                        ) {}
                        super.onPageFinished(view, url)
                    }

                    override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: android.webkit.WebResourceError?) {
                        val desc = error?.description ?: "unknown"
                        val code = error?.errorCode ?: -1
                        Log.e(TAG, "onReceivedError url=${request?.url} code=$code desc=$desc")
                        super.onReceivedError(view, request, error)
                    }
                }
                Log.d(TAG, "loading url=$url")
                loadUrl(url)
            }
        },
        update = { web ->
            val current = web.url ?: ""
            if (!current.contains(symbol) || !current.contains(tf)) {
                Log.d(TAG, "update reload symbol=$symbol tf=$tf current=$current")
                web.loadUrl(url)
            }
        },
    )
}
