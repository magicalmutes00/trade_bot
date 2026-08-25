package com.bofedge.app

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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import com.bofedge.core.ui.components.DashboardSkeleton
import com.bofedge.core.ui.components.EmptyState
import com.bofedge.domain.model.AuthUser
import com.bofedge.domain.model.RealtimeConnection

@Composable
fun DashboardTab(mainViewModel: MainViewModel, realtimeViewModel: RealtimeViewModel) {
    val dashboard by mainViewModel.dashboard.collectAsStateWithLifecycle()
    val realtime by realtimeViewModel.state.collectAsStateWithLifecycle()

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        when (val d = dashboard) {
            DashboardUiState.Loading -> DashboardSkeleton()

            is DashboardUiState.Error -> Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.error.copy(alpha = 0.1f),
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(14.dp)) {
                    Text(d.message, color = MaterialTheme.colorScheme.error,
                         style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.height(6.dp))
                    Button(onClick = mainViewModel::refreshDashboard) { Text("Retry") }
                }
            }

            is DashboardUiState.Ready -> {
                MarketStatusCard(
                    status = d.snapshot.marketStatus.status,
                    market = d.snapshot.marketStatus.market,
                    connection = realtime.connection,
                )
                Spacer(Modifier.height(12.dp))
                BofSummaryCard(d.snapshot.bofSummary)
                Spacer(Modifier.height(16.dp))
                LiveMoversCard(realtime.ticks)
                Spacer(Modifier.height(16.dp))
                SignalFeedSection("Strongest signals", d.snapshot.strongestSignals)
                Spacer(Modifier.height(16.dp))
                SignalFeedSection("Latest signals", d.snapshot.latestSignals.take(5))
            }
        }

        EmptyState(title = "", description = "", modifier = Modifier.height(0.dp))

        // Bottom padding so content clears the nav bar
        Spacer(Modifier.height(72.dp))
    }
}

@Composable
private fun MarketStatusCard(status: String, market: String,
                             connection: RealtimeConnection = RealtimeConnection.OFFLINE) {
    val dotColor = when (status) {
        "OPEN" -> Color(0xFF16C784); "PRE_OPEN" -> Color(0xFFB58500); else -> Color(0xFF8A97A8)
    }
    val liveLabel = when (connection) {
        RealtimeConnection.LIVE -> "LIVE"
        RealtimeConnection.CONNECTING -> "connecting…"
        RealtimeConnection.RECONNECTING -> "reconnecting…"
        else -> "offline"
    }
    val liveColor =
        if (connection == RealtimeConnection.LIVE) Color(0xFF16C784) else Color(0xFF8A97A8)

    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(dotColor))
            Spacer(Modifier.size(10.dp))
            Column(Modifier.weight(1f)) {
                Text("$market · ${status.replace('_', ' ').lowercase()
                        .replaceFirstChar { it.uppercase() }}",
                     style = MaterialTheme.typography.titleSmall)
                Text("Session times from real clock (09:15–15:30 IST)",
                     style = MaterialTheme.typography.labelSmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Text(liveLabel, style = MaterialTheme.typography.labelSmall,
                 color = liveColor, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun BofSummaryCard(summary: com.bofedge.domain.model.BofSummary) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp)) {
            Text("BOF summary — today", style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                SummaryStat("Active", summary.activeTotal)
                SummaryStat("Bullish", summary.bullish)
                SummaryStat("Bearish", summary.bearish)
            }
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                SummaryStat("Strong", summary.strong)
                SummaryStat("New", summary.newToday)
                SummaryStat("Detected", summary.detectedToday)
            }
        }
    }
}

@Composable
private fun SummaryStat(label: String, value: Int) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelSmall,
             color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun LiveMoversCard(ticks: Map<String, com.bofedge.domain.model.QuoteTick>) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Live ticks", style = MaterialTheme.typography.titleSmall)
                Text("${ticks.size} streaming", style = MaterialTheme.typography.labelSmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.height(10.dp))
            if (ticks.isEmpty()) {
                Text("Waiting for first tick…", style = MaterialTheme.typography.bodyMedium,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                ticks.values.sortedByDescending { kotlin.math.abs(it.changePct ?: 0.0) }
                    .take(5).forEach { tick ->
                        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp),
                            horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(tick.symbol, style = MaterialTheme.typography.bodyMedium,
                                 fontWeight = FontWeight.Medium)
                            Text(buildString {
                                append("%.2f".format(tick.lastPrice))
                                tick.changePct?.let { append("   %+.2f%%".format(it)) }
                            }, style = MaterialTheme.typography.bodyMedium,
                               color = if ((tick.changePct ?: 0.0) >= 0) Color(0xFF16C784)
                                       else Color(0xFFEA3943))
                        }
                    }
            }
        }
    }
}

@Composable
private fun SignalFeedSection(title: String, signals: List<com.bofedge.domain.model.SignalCard>) {
    Text(title, style = MaterialTheme.typography.titleSmall)
    Spacer(Modifier.height(8.dp))
    if (signals.isEmpty()) {
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Text("No signals in this feed yet.", style = MaterialTheme.typography.bodyMedium,
                 color = MaterialTheme.colorScheme.onSurfaceVariant,
                 modifier = Modifier.padding(14.dp))
        }
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        signals.forEach { signal ->
            val bull = signal.direction == "BULLISH"
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Row(Modifier.fillMaxWidth().clickable { }.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).clip(CircleShape)
                            .background(if (bull) Color(0xFF16C784) else Color(0xFFEA3943)))
                    Spacer(Modifier.size(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text("${signal.symbol} · ${signal.timeframe}",
                             fontWeight = FontWeight.SemiBold)
                        Text("${signal.direction.lowercase()} BOF @ ${"%.2f".format(signal.bofLevel)}",
                             style = MaterialTheme.typography.labelSmall,
                             color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(signal.strength.lowercase().replace('_', ' '),
                             color = MaterialTheme.colorScheme.primary,
                             style = MaterialTheme.typography.labelSmall)
                        Text("${(signal.confidence * 100).toInt()}%",
                             style = MaterialTheme.typography.labelSmall,
                             color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
fun ProfileTab(mainViewModel: MainViewModel, prefsViewModel: NotificationPrefsViewModel) {
    val profile by mainViewModel.profile.collectAsStateWithLifecycle()
    val prefsState by prefsViewModel.state.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
           verticalArrangement = Arrangement.spacedBy(16.dp)) {
        when (val p = profile) {
            ProfileUiState.Loading -> Card(Modifier.fillMaxWidth()) {
                Box(Modifier.fillMaxWidth().height(72.dp), contentAlignment = Alignment.Center) {
                    Text("Loading…")
                }
            }
            is ProfileUiState.Error -> Card(Modifier.fillMaxWidth()) {
                Text(p.message, color = MaterialTheme.colorScheme.error,
                     modifier = Modifier.padding(14.dp))
            }
            is ProfileUiState.Ready -> Card(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(44.dp).clip(CircleShape)
                            .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.18f)),
                        contentAlignment = Alignment.Center) {
                        Text(initialsFor(p.user), color = MaterialTheme.colorScheme.primary,
                             fontWeight = FontWeight.Bold)
                    }
                    Spacer(Modifier.size(12.dp))
                    Column {
                        Text(p.user.displayName ?: p.user.email.substringBefore('@'),
                             style = MaterialTheme.typography.titleSmall)
                        Text(p.user.email, style = MaterialTheme.typography.labelMedium,
                             color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Signed in with ${p.user.authProvider.lowercase()}",
                             style = MaterialTheme.typography.labelSmall,
                             color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }

        EmptyState(title = "Settings", description = "Full settings arrive in later phases.")
    }
}

private fun initialsFor(user: AuthUser): String =
    user.displayName?.split(' ')?.take(2)?.mapNotNull { it.firstOrNull()?.uppercase() }?.joinToString("")
        ?: user.email.take(2).uppercase()
