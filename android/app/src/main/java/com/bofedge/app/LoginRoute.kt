package com.bofedge.app

import androidx.compose.runtime.Composable
import com.bofedge.feature.auth.presentation.AuthState
import com.bofedge.feature.auth.presentation.AuthViewModel
import com.bofedge.feature.auth.presentation.LoginScreen

/**
 * Login route wrapper: keeps MainActivity's when-block readable and owns the
 * activity-context handoff required by Credential Manager.
 */
@Composable
fun LoginRoute(authViewModel: AuthViewModel, state: AuthState) {
    LoginScreen(
        state = state,
        onGoogleSignIn = { context ->
            authViewModel.signInWithGoogle(context)
        },
    )
}
