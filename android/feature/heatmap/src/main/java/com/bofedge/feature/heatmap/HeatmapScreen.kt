package com.bofedge.feature.heatmap.presentation

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bofedge.core.ui.components.EmptyState
import com.bofedge.domain.model.HeatmapCell

/** Green/red intensity scale from %Î” (clamped Â±2%). */
private fun cellColor(changePct: Double?): Color? {
    if (changePct == null) return null
    val clamped = changePct.coerceIn(-2.0, 2.0)
    val alpha = 0.15f + (kotlin.math.abs(clamped) / 2.0 * 0.65).toFloat()
    return if (clamped >= 0) Color(0xFF16C784).copy(alpha = alpha)
    else Color(0xFFEA3943).copy(alpha = alpha)
}

@Composable
fun HeatmapRoute(onOpenInstrument: (String) -> Unit, viewModel: HeatmapViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                selected = state.groupBySector,
                onClick = viewModel::toggleGrouping,
                label = { Text("By sector") },
            )
            FilterChip(
                selected = !state.groupBySector,
                onClick = viewModel::toggleGrouping,
                label = { Text("By type") },
            )
            Spacer(Modifier.weight(1f))
            FilterChip(
                selected = state.onlyWithSignals,
                onClick = viewModel::toggleOnlySignals,
                label = { Text("Signals only") },
            )
        }

        when {
            state.error != null && state.groups.isEmpty() -> EmptyState(
                title = "Couldn't load heatmap",
                description = state.error,
                actionLabel = "Retry",
                onAction = viewModel::refresh,
            )
            state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
            else -> HeatmapGrid(state, onOpenInstrument)
        }
    }
}

@Composable
private fun HeatmapGrid(state: HeatmapUiState, onOpenInstrument: (String) -> Unit) {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(minSize = 110.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        state.groups.forEach { group ->
            item(key = "header-${group.key}") {
                Text(
                    "${group.label} (${group.cells.size})",
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(top = 8.dp, start = 4.dp, bottom = 2.dp),
                )
            }
            items(group.cells, key = { it.instrumentId }) { cell ->
                HeatmapCellView(cell) { onOpenInstrument(cell.instrumentId) }
            }
        }
        if (state.groups.isEmpty()) {
            item { EmptyState(title = "Nothing to show", description = "No instruments match these filters.") }
        }
    }
}

@Composable
private fun HeatmapCellView(cell: HeatmapCell, onClick: () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(1.25f)
            .clickable(onClick = onClick),
    ) {
        Box(Modifier.fillMaxSize().background(cellColor(cell.changePct) ?: Color.Transparent)) {
            Column(Modifier.padding(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (cell.bofDirection != null) {
                        val bull = cell.bofDirection == "BULLISH"
                        Box(
                            Modifier.size(8.dp).clip(CircleShape)
                                .background(if (bull) Color(0xFF16C784) else Color(0xFFEA3943)),
                        )
                        Spacer(Modifier.width(4.dp))
                    }
                    Text(cell.symbol, fontWeight = FontWeight.SemiBold, maxLines = 1)
                }
                Spacer(Modifier.height(4.dp))
                cell.lastPrice?.let {
                    Text("%.2f".format(it), style = MaterialTheme.typography.bodyMedium)
                } ?: Text("â€”", style = MaterialTheme.typography.bodyMedium,
                          color = MaterialTheme.colorScheme.onSurfaceVariant)
                cell.changePct?.let {
                    Text("%+.2f%%".format(it), style = MaterialTheme.typography.labelSmall,
                         color = if (it >= 0) Color(0xFF16C784) else Color(0xFFEA3943))
                }
                cell.bofStrength?.let {
                    Text(it.lowercase().replace('_', ' '),
                         style = MaterialTheme.typography.labelSmall,
                         color = MaterialTheme.colorScheme.primary)
                }
            }
        }
    }
}

