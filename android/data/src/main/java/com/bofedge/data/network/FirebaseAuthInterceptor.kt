package com.bofedge.data.network

import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Attaches `Authorization: Bearer <Firebase ID Token>` to outgoing API calls.
 *
 * - Tokens are obtained through the Firebase SDK (`getIdToken(false)`), which
 *   caches and refreshes them automatically — no custom refresh logic.
 * - The token is NEVER logged and is never attached to the token-exchange call
 *   itself (it travels in that request's body by contract).
 */
class FirebaseAuthInterceptor(
    private val firebaseAuth: FirebaseAuth?,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()

        if (request.url.encodedPath.endsWith("/auth/firebase")) {
            return chain.proceed(request)
        }

        val token = currentValidToken()
        val authorized = if (token.isNullOrBlank()) {
            request
        } else {
            request.newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        }
        return chain.proceed(authorized)
    }

    private fun currentValidToken(): String? = try {
        val user = firebaseAuth?.currentUser ?: return null
        runBlocking { user.getIdToken(false).await().token }
    } catch (_: Exception) {
        null // never break the request chain because a token refresh failed
    }
}
