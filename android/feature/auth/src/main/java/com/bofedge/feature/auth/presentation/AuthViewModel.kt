package com.bofedge.feature.auth.presentation

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.domain.error.AuthError
import com.bofedge.domain.model.AuthUser
import com.bofedge.domain.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<AuthState>(AuthState.Checking)
    val state: StateFlow<AuthState> = _state.asStateFlow()

    init {
        // Cold-start resolution: no login flash for already signed-in users.
        val user: AuthUser? = authRepository.currentUserOrNull()
        _state.value = if (user != null) {
            AuthState.Authenticated(user)
        } else {
            AuthState.Unauthenticated
        }
    }

    fun signInWithGoogle(activityContext: Context) {
        if (_state.value is AuthState.Loading) return

        _state.update { AuthState.Loading("Signing you in…") }
        viewModelScope.launch {
            authRepository.signInWithGoogle(activityContext)
                .onSuccess { user ->
                    _state.value = AuthState.Authenticated(user)
                }
                .onFailure { error ->
                    when (error) {
                        is CancellationException -> {
                            _state.value = AuthState.Unauthenticated
                            throw error
                        }
                        is AuthError -> _state.value = AuthState.Error(error.userMessage())
                        else -> _state.value =
                            AuthState.Error(GENERIC_FAILURE)
                    }
                }
        }
    }

    /** Signs out (Firebase + local state); never deletes the account. */
    fun logout(context: Context) {
        viewModelScope.launch {
            try {
                authRepository.signOut(context)
            } catch (_: Exception) {
                // Logout is best-effort; local state clears regardless.
            } finally {
                _state.value = AuthState.Unauthenticated
            }
        }
    }

    fun clearError() {
        if (_state.value is AuthState.Error) {
            _state.value = AuthState.Unauthenticated
        }
    }
}

/** User-facing copy per spec §18 — no stack traces, SDK codes, or tokens. */
fun AuthError.userMessage(): String = when (this) {
    AuthError.Cancelled -> "Google Sign-In was cancelled."
    AuthError.NoGoogleAccount ->
        "No Google account was selected. Add or enable a Google account on this device and try again."
    AuthError.GoogleUnavailable -> "Unable to connect to Google. Check your connection and try again."
    is AuthError.FirebaseFailure -> when (reason) {
        AuthError.FirebaseFailure.Reason.INVALID_CREDENTIAL -> "Firebase authentication failed. Please try again."
        AuthError.FirebaseFailure.Reason.SESSION_EXPIRED -> "Your session has expired. Please sign in again."
        AuthError.FirebaseFailure.Reason.CONFIGURATION -> "Google Sign-In is not configured on this build."
        AuthError.FirebaseFailure.Reason.OTHER -> "Firebase authentication failed. Please try again."
    }
    is AuthError.BackendFailure -> "Unable to connect to the BOF server. Please try again shortly."
    is AuthError.Unknown -> GENERIC_FAILURE
}

const val GENERIC_FAILURE: String = "Something went wrong. Please try again."
