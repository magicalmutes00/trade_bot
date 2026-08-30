package com.bofedge.feature.auth.presentation

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/**
 * Login screen (spec §6):
 *
 *   BOF Edge
 *   Market Intelligence
 *   Breakout Failure Scanner
 *   [ Continue with Google ]
 *   By continuing, you agree to the application's Terms and Privacy Policy.
 */
@Composable
fun LoginScreen(
    state: AuthState,
    onGoogleSignIn: (activityContext: android.content.Context) -> Unit,
    modifier: Modifier = Modifier,
) {
    val isLoading = state is AuthState.Loading
    val activityContext = androidx.compose.ui.platform.LocalContext.current

    Surface(modifier = modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.weight(0.28f))

            // --- Brand block ---
            Text(
                text = "TradeBot",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(10.dp))
            Text(
                text = "Market Intelligence",
                style = MaterialTheme.typography.titleLarge,
            )
            Text(
                text = "Breakout Failure Scanner",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.weight(0.16f))

            // --- Error banner ---
            if (state is AuthState.Error) {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.error.copy(alpha = 0.12f),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        text = state.message,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(12.dp),
                    )
                }
                Spacer(Modifier.height(20.dp))
            }

            // --- Google button (branding-compliant icon, no fake logo) ---
            Button(
                onClick = { onGoogleSignIn(activityContext) },
                enabled = !isLoading,
                shape = RoundedCornerShape(24.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color.White,
                    contentColor = Color(0xFF1F1F1F),
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        strokeWidth = 2.dp,
                        modifier = Modifier.size(22.dp),
                    )
                    Spacer(Modifier.size(12.dp))
                    Text(
                        text = (state as? AuthState.Loading)?.message ?: "Signing in…",
                        style = MaterialTheme.typography.titleSmall,
                    )
                } else {
                    Image(
                        painter = painterResource(id = com.bofedge.feature.auth.R.drawable.ic_google_g),
                        contentDescription = "Google logo",
                        modifier = Modifier.size(22.dp),
                    )
                    Spacer(Modifier.size(12.dp))
                    Text("Continue with Google", style = MaterialTheme.typography.titleSmall)
                }
            }

            Spacer(Modifier.height(18.dp))

            Text(
                text = "By continuing, you agree to the application's Terms and Privacy Policy.",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.weight(0.32f))
        }
    }
}
