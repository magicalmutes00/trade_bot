package com.bofedge.domain.repository

import android.content.Context
import com.bofedge.domain.error.AuthError
import com.bofedge.domain.model.AuthUser

/**
 * Authentication gateway backed by Firebase Authentication + the BOF backend.
 *
 * Flow (spec §1):
 *   Google Sign-In → Firebase credential → Firebase user → Firebase ID token
 *   → FastAPI verification → PostgreSQL user sync → application session.
 */
interface AuthRepository {

    /**
     * Launches Google Sign-In ([context] must be an Activity context),
     * exchanges the resulting credential with Firebase, then verifies the
     * Firebase ID token against the backend.
     */
    suspend fun signInWithGoogle(context: Context): Result<AuthUser>

    /** Current signed-in user from Firebase state (no network), or null. */
    fun currentUserOrNull(): AuthUser?

    /** A fresh Firebase ID token for authenticated API calls, or null. */
    suspend fun freshIdToken(): String?

    /** Signs out of Firebase and clears local auth state. Never deletes the account. */
    suspend fun signOut(context: Context)
}

/** Maps repository failures to typed errors without exposing SDK internals. */
fun Exception.toAuthError(): AuthError = AuthError.BackendFailure(code = null, message = localizedMessage)
