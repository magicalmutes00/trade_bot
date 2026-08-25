package com.bofedge.core.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

private fun Modifier.shimmer(): Modifier = composed {
    val transition = rememberInfiniteTransition(label = "shimmer")
    val progress by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1100, easing = LinearEasing)),
        label = "shimmerProgress",
    )
    val base = MaterialTheme.colorScheme.surfaceVariant
    val hi = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f)
    background(
        Brush.linearGradient(
            colors = listOf(base, hi, base),
            start = Offset(progress * 600f - 300f, 0f),
            end = Offset(progress * 600f, 100f),
        ),
    )
}

/** Rectangular shimmer block matching the content it replaces. */
@Composable
fun ShimmerBox(width: Dp, height: Dp, corner: Dp = 8.dp) {
    Box(
        Modifier
            .width(width)
            .height(height)
            .clip(RoundedCornerShape(corner))
            .shimmer(),
    )
}

/** Full-width skeleton row for list items. */
@Composable
fun ShimmerListRow(modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Box(Modifier.size(44.dp).clip(CircleShape).shimmer())
        Spacer(Modifier.width(12.dp))
        Column(verticalArrangement = Arrangement.Center) {
            Box(Modifier.width(120.dp).height(14.dp).clip(RoundedCornerShape(4.dp)).shimmer())
            Spacer(Modifier.height(6.dp))
            Box(Modifier.width(180.dp).height(10.dp).clip(RoundedCornerShape(4.dp)).shimmer())
        }
    }
}

/** Full dashboard skeleton — market card + summary + feed rows. */
@Composable
fun DashboardSkeleton() {
    Column(Modifier.fillMaxWidth().padding(16.dp)) {
        // Market status skeleton
        ShimmerBox(width = Dp.Unspecified, height = 64.dp)
        Spacer(Modifier.height(12.dp))

        // BOF summary skeleton (2 rows × 3 stats)
        ShimmerBox(width = Dp.Unspecified, height = 96.dp)
        Spacer(Modifier.height(12.dp))

        // Signal feed rows
        repeat(4) {
            ShimmerListRow()
            Spacer(Modifier.height(8.dp))
        }
    }
}

/** Scanner list skeleton. */
@Composable
fun ScannerSkeleton(rows: Int = 6) {
    Column { repeat(rows) { ShimmerListRow() } }
}
