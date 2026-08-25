package com.bofedge.feature.scanner.presentation

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bofedge.core.ui.components.EmptyState
import com.bofedge.domain.model.Instrument
import com.bofedge.domain.repository.InstrumentSort

private val TYPE_FILTERS = listOf(
    null to "All",
    "STOCK" to "Stocks",
    "INDEX" to "Indices",
    "COMMODITY" to "Commodities",
    "FOREX" to "Forex",
    "CRYPTO" to "Crypto",
)

private val SORTS = listOf(
    InstrumentSort.SYMBOL to "Aâ€“Z",
    InstrumentSort.NAME to "Name",
    InstrumentSort.CHANGE_PCT to "% change",
    InstrumentSort.VOLUME to "Volume",
)

/** Scanner tab (Phase 2): search + category filters + sort + server pagination. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScannerRoute(
    onOpenInstrument: (String) -> Unit,
    viewModel: ScannerViewModel,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = state.query,
            onValueChange = viewModel::onQueryChange,
            singleLine = true,
            placeholder = { Text("Search symbol or nameâ€¦") },
            leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TYPE_FILTERS.forEach { (wire, label) ->
                FilterChip(
                    selected = state.typeFilter == wire,
                    onClick = { viewModel.onTypeFilterChange(wire) },
                    label = { Text(label) },
                )
            }
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "Sort",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            SORTS.forEach { (sort, label) ->
                FilterChip(
                    selected = state.sort == sort,
                    onClick = { viewModel.onSortChange(sort) },
                    label = { Text(label) },
                )
            }
        }

    when {
            state.showInitialError -> EmptyState(
                title = "Couldn't load instruments",
                description = state.error,
                actionLabel = "Retry",
                onAction = viewModel::refresh,
            )
            state.loading && state.items.isEmpty() -> Box(
                Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }
            else -> InstrumentList(
                state = state,
                onOpenInstrument = onOpenInstrument,
                onLoadMore = viewModel::loadMore,
                onAddToWatchlist = viewModel::openWatchlistPicker,
            )
        }

        if (state.showWatchlistPicker) {
            val target = state.pickerInstrumentId
            if (target != null) {
                WatchlistPickerDialog(
                    lists = state.watchlists,
                    onPick = { viewModel.addToWatchlist(it, target) },
                    onCreateNew = { viewModel.addToWatchlist(null, target) },
                    onDismiss = viewModel::dismissWatchlistPicker,
                )
            }
        }
    }
}

@Composable
private fun InstrumentList(
    state: ScannerUiState,
    onOpenInstrument: (String) -> Unit,
    onLoadMore: () -> Unit,
    onAddToWatchlist: (String) -> Unit,
) {
    if (state.items.isEmpty()) {
        EmptyState(title = "No instruments match", description = "Try a different search or filter.")
        return
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(state.items, key = { it.id }) { instrument ->
            InstrumentRow(
                instrument = instrument,
                onClick = { onOpenInstrument(instrument.id) },
                onStar = { onAddToWatchlist(instrument.id) },
            )
        }
        item(key = "footer") {
            // Auto-paginate: when the footer scrolls into composition, fetch next page.
            LaunchedEffect(
                state.items.size, state.query, state.typeFilter, state.sort,
            ) {
                if (!state.endReached && !state.appending && !state.loading) onLoadMore()
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                contentAlignment = Alignment.Center,
            ) {
                when {
                    state.appending -> CircularProgressIndicator(strokeWidth = 2.dp)
                    state.endReached -> Text(
                        "Showing all ${state.total}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun InstrumentRow(instrument: Instrument, onClick: () -> Unit, onStar: () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Row(
            Modifier.padding(start = 14.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(instrument.symbol, fontWeight = FontWeight.SemiBold)
                Text(
                    instrument.name,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    instrument.type.lowercase().replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
                instrument.sectorName?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                    )
                }
            }
            IconButton(onClick = onStar) {
                Icon(Icons.Filled.Star, contentDescription = "Add to watchlist",
                     tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun WatchlistPickerDialog(
    lists: List<com.bofedge.domain.model.Watchlist>,
    onPick: (String) -> Unit,
    onCreateNew: () -> Unit,
    onDismiss: () -> Unit,
) {
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add to watchlist") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (lists.isEmpty()) {
                    Text("No watchlists yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                lists.forEach { wl ->
                    FilterChip(selected = false, onClick = { onPick(wl.id) },
                               label = { Text(wl.name) })
                }
                FilterChip(selected = false, onClick = onCreateNew,
                           label = { Text("+ New list") })
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}




