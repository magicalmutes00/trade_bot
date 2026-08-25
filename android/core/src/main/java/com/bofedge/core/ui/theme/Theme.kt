package com.bofedge.core.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val DarkScheme = darkColorScheme(
    primary = BofAccent,
    onPrimary = BofBlack,
    background = BofBlack,
    onBackground = BofTextPrimary,
    surface = BofSurface,
    onSurface = BofTextPrimary,
    surfaceVariant = BofSurfaceHigh,
    onSurfaceVariant = BofTextSecondary,
    outline = BofBorder,
    error = BofRed,
)

private val LightScheme = lightColorScheme(
    primary = BofAccent,
    background = BofLightBackground,
    onBackground = BofLightTextPrimary,
    surface = BofLightSurface,
    onSurface = BofLightTextPrimary,
    surfaceVariant = BofLightBorder,
    onSurfaceVariant = BofLightTextSecondary,
    outline = BofLightBorder,
    error = BofRed,
)

@Composable
fun BofEdgeTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkScheme else LightScheme,
        typography = BofTypography,
        content = content,
    )
}
