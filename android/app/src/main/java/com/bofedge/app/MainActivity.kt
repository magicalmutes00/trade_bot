package com.bofedge.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bofedge.core.ui.theme.BofEdgeTheme
import com.bofedge.feature.auth.presentation.AuthState
import com.bofedge.feature.auth.presentation.AuthViewModel
import dagger.hilt.android.AndroidEntryPoint
import androidx.hilt.navigation.compose.hiltViewModel

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            BofEdgeTheme {
                val authViewModel: AuthViewModel = hiltViewModel()
                val authState by authViewModel.state.collectAsStateWithLifecycle()

                when (val state = authState) {
                    AuthState.Checking -> SplashScreen()

                    is AuthState.Unauthenticated,
                    is AuthState.Loading,
                    is AuthState.Error -> LoginRoute(authViewModel, state)

                    is AuthState.Authenticated -> MainShell(user = state.user)
                }
            }
        }
    }
}
