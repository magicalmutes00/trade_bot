package com.bofedge.feature.watchlist.presentation

import androidx.compose.foundation.background
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bofedge.core.ui.components.EmptyState

@Composable
fun WatchlistRoute(onOpenInstrument: (String) -> Unit, viewModel: WatchlistViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize()) {
        // --- list selector row ---
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            state.lists.forEach { wl ->
                FilterChip(
                    selected = state.selectedId == wl.id,
                    onClick = { viewModel.select(wl.id) },
                    label = { Text(wl.name) },
                )
            }
            Spacer(Modifier.weight(1f))
            IconButton(onClick = viewModel::startCreate) {
                Icon(Icons.Filled.Add, contentDescription = "New watchlist")
            }
            if (state.selectedId != null) {
                IconButton(onClick = viewModel::deleteSelected) {
                    Icon(Icons.Filled.Delete, contentDescription = "Delete watchlist")
                }
            }
        }

        when {
            state.error != null && state.lists.isEmpty() -> EmptyState(
                title = "Couldn't load watchlists",
                description = state.error,
                actionLabel = "Retry",
                onAction = viewModel::refresh,
            )
            state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
            state.lists.isEmpty() -> EmptyState(
                title = "No watchlists yet",
                description = "Tap + to create your first watchlist.",
                actionLabel = "Create",
                onAction = viewModel::startCreate,
            )
            else -> ItemsList(state, onOpenInstrument, viewModel)
        }
    }

    if (state.showCreateDialog) {
        CreateWatchlistDialog(
            name = state.newName,
            onNameChange = viewModel::onNameChange,
            onConfirm = viewModel::confirmCreate,
            onDismiss = viewModel::dismissCreate,
        )
    }
}

@Composable
private fun ItemsList(
    state: WatchlistUiState,
    onOpenInstrument: (String) -> Unit,
    viewModel: WatchlistViewModel,
) {
    val selected = state.lists.firstOrNull { it.id == state.selectedId }
    val entries = selected?.entries.orEmpty()
    if (entries.isEmpty()) {
        EmptyState(title = "This list is empty", description = "Add instruments from the Scanner (star icon).")
        return
    }

    LazyColumn(
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(entries, key = { it.instrumentId }) { e ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Row(
                    Modifier.fillMaxWidth().padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f).clickable { onOpenInstrument(e.instrumentId) }) {
                        Text(e.symbol, fontWeight = FontWeight.SemiBold)
                        Text(
                            e.name,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                        )
                        if (e.bofDirection != null) {
                            Text(
                                "${e.bofDirection?.lowercase()} BOF · ${e.bofStrength?.lowercase()?.replace('_', ' ')}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        e.lastPrice?.let {
                            Text("%.2f".format(it), fontWeight = FontWeight.Medium)
                        } ?: Text("—", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        e.changePct?.let {
                            Text("%+.2f%%".format(it),
                                 style = MaterialTheme.typography.labelSmall,
                                 color = if (it >= 0) Color(0xFF16C784) else Color(0xFFEA3943))
                        }
                    }
                    IconButton(onClick = { viewModel.toggleAlert(e.instrumentId, !e.alertEnabled) }) {
                        Icon(
                            if (e.alertEnabled) Icons.Filled.Notifications else Icons.Outlined.Notifications,
                            contentDescription = if (e.alertEnabled) "Alerts on" else "Alerts off",
                            tint = if (e.alertEnabled) MaterialTheme.colorScheme.primary
                                   else MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    IconButton(onClick = { viewModel.removeItem(e.instrumentId) }) {
                        Icon(Icons.Filled.Close, contentDescription = "Remove",
                             tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun CreateWatchlistDialog(
    name: String,
    onNameChange: (String) -> Unit,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New watchlist") },
        text = {
            OutlinedTextField(
                value = name,
                onValueChange = onNameChange,
                singleLine = true,
                placeholder = { Text("Name") },
            )
        },
        confirmButton = {
            TextButton(onClick = onConfirm, enabled = name.isNotBlank()) { Text("Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
