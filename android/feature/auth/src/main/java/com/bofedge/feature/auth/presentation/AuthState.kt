package com.bofedge.feature.auth.presentation

import com.bofedge.domain.model.AuthUser

/** Authentication lifecycle states (spec §16). */
sealed class AuthState {
    /** Determining Firebase session on cold start — splash is shown. */
    object Checking : AuthState()

    /** No signed-in user; show the login screen. */
    object Unauthenticated : AuthState()

    /** A sign-in / sign-out operation is in flight. */
    data class Loading(val message: String? = null) : AuthState()

    /** Sign-in succeeded; protected UI may be shown. */
    data class Authenticated(val user: AuthUser) : AuthState()

    /** Last sign-in attempt failed; login screen shows the message. */
    data class Error(val message: String) : AuthState()
}
