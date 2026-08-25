package com.bofedge.data.network

import java.io.IOException
import okhttp3.Interceptor
import okhttp3.Response

/**
 * One automatic retry for failed GET requests — covers transient drops and
 * Render free-tier cold-start windows where the first connect times out.
 *
 * Only idempotent GETs retry; writes never replay automatically.
 */
class RetryOnceOnIOException(
    private val pauseMillis: Long = 600,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()

        if (!request.method.equals("GET", ignoreCase = true)) {
            return chain.proceed(request)
        }

        return try {
            chain.proceed(request)
        } catch (first: IOException) {
            try {
                Thread.sleep(pauseMillis)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
                throw first
            }
            try {
                chain.proceed(request)
            } catch (second: IOException) {
                throw second // caller surfaces Offline / triggers its own retry UI
            }
        }
    }
}
