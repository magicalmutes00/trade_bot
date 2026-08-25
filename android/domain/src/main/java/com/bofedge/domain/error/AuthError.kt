package com.bofedge.domain.error

/**
 * Typed authentication failures. Extends [RuntimeException] so failures can
 * be thrown through suspend boundaries and caught as one family; presentation
 * maps them to user-friendly copy — raw SDK/exception details never reach UI.
 */
sealed class AuthError : RuntimeException() {
    /** User closed the Google account picker / cancelled consent. */
    object Cancelled : AuthError()

    /** No Google accounts available on the device or none usable. */
    object NoGoogleAccount : AuthError()

    /** Play Services / network problem while talking to Google. */
    object GoogleUnavailable : AuthError()

    /** Firebase rejected the credential (invalid/expired/revoked). */
    data class FirebaseFailure(val reason: Reason) : AuthError() {
        enum class Reason { INVALID_CREDENTIAL, SESSION_EXPIRED, CONFIGURATION, OTHER }
    }

    /** Backend unreachable or returned a non-2xx for the token exchange. */
    data class BackendFailure(
        val code: String?,
        override val message: String?,
    ) : AuthError()

    /** Anything unexpected — details are logged, never shown. */
    data class Unknown(override val cause: Throwable? = null) : AuthError()
}
