package com.bofedge.core.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Price text that flashes green/red for ~600 ms whenever `value` changes,
 * then settles back to the base colour. Used on live tick displays.
 */
@Composable
fun FlashPrice(
    value: Double,
    modifier: Modifier = Modifier,
    suffix: String = "",
    decimals: Int = 2,
    upColor: Color = Color(0xFF16C784),
    downColor: Color = Color(0xFFEA3943),
) {
    val prev = remember { mutableStateOf(value) }
    val flash = remember { mutableStateOf<Color?>(null) }

    LaunchedEffect(value) {
        if (value > prev.value) flash.value = upColor.copy(alpha = 0.85f)
        else if (value < prev.value) flash.value = downColor.copy(alpha = 0.85f)
        prev.value = value
        kotlinx.coroutines.delay(600)
        flash.value = null
    }

    val animated by animateColorAsState(
        targetValue = flash.value ?: MaterialTheme.colorScheme.onSurface,
        animationSpec = tween(durationMillis = 400),
        label = "flashPrice",
    )

    Text(
        text = "%.${decimals}f".format(value) + suffix,
        color = animated,
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        modifier = modifier,
    )
}
