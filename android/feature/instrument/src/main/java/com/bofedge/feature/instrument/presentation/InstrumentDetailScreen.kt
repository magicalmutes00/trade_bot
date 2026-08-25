package com.bofedge.feature.instrument.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bofedge.core.ui.components.EmptyState
import com.bofedge.feature.instrument.chart.CandleChartMath
import com.bofedge.feature.instrument.chart.ChartColors
import com.bofedge.feature.instrument.chart.KiteStyleChart
import com.bofedge.domain.model.InstrumentDetail

private val TIMEFRAMES = listOf("15m", "1h", "4h", "1D")


/** Instrument detail page (Phase 2). Chart canvas + overlays arrive in Phase 3. */
@Composable
fun InstrumentDetailRoute(
    viewModel: InstrumentDetailViewModel,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val candleState by viewModel.candles.collectAsStateWithLifecycle()
    when (val s = state) {
        InstrumentDetailUiState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
            CircularProgressIndicator()
        }
        is InstrumentDetailUiState.Error -> EmptyState(
            title = "Couldn't load instrument",
            description = s.message,
            actionLabel = "Retry",
            onAction = viewModel::load,
        )
        is InstrumentDetailUiState.Ready -> InstrumentDetailContent(
            detail = s.detail,
            candleState = candleState,
            onTimeframeChange = viewModel::onTimeframeChange,
            onRetryCandles = viewModel::loadCandles,
        )
    }
}

@Composable
private fun InstrumentDetailContent(
    detail: InstrumentDetail,
    candleState: CandlesUiState,
    onTimeframeChange: (String) -> Unit,
    onRetryCandles: () -> Unit,
) {
    var selectedTimeframe by rememberSaveable { mutableStateOf(candleState.timeframe) }
    var showSma by rememberSaveable { mutableStateOf(false) }
    var showEma9 by rememberSaveable { mutableStateOf(false) }
    var showBb by rememberSaveable { mutableStateOf(false) }
    var showRsi by rememberSaveable { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        // --- Header ---
        Text(detail.symbol, style = MaterialTheme.typography.headlineMedium)
        Text(
            detail.name,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            AssistChip(onClick = {}, label = { Text(detail.exchange) }, enabled = false)
            AssistChip(onClick = {}, label = { Text(detail.type.lowercase()) }, enabled = false)
            detail.sectorName?.let {
                AssistChip(onClick = {}, label = { Text(it, maxLines = 1) }, enabled = false)
            }
        }

        Spacer(Modifier.height(16.dp))

        // --- Price block: honest empty state until provider lands ---
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Box(Modifier.fillMaxWidth().padding(20.dp), contentAlignment = Alignment.Center) {
                val q = detail.quote
                if (q?.lastPrice != null) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            "${detail.currency} ${"%.2f".format(q.lastPrice)}",
                            style = MaterialTheme.typography.headlineMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        q.changePct?.let {
                            val up = it >= 0
                            Text(
                                "%+.2f%%".format(it),
                                color = if (up) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                } else {
                    Text(
                        "Live quotes arrive with the market-data provider (Phase 3)",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // --- Timeframe selector (visual; wired to candles in Phase 3) ---
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            TIMEFRAMES.forEach { tf ->
                FilterChip(
                    selected = selectedTimeframe == tf,
                    onClick = { selectedTimeframe = tf },
                    label = { Text(tf) },
                )
            }
        }
        // --- Timeframe selector (drives candle loads) ---
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            TIMEFRAMES.forEach { tf ->
                FilterChip(
                    selected = selectedTimeframe == tf,
                    onClick = {
                        selectedTimeframe = tf
                        onTimeframeChange(tf)
                    },
                    label = { Text(tf) },
                )
            }
        }
        Spacer(Modifier.height(6.dp))

        // --- Indicator toggle chips ---
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            FilterChip(selected = showSma, onClick = { showSma = !showSma },
                       label = { Text("MA20", color = ChartColors.SMA20) })
            FilterChip(selected = showEma9, onClick = { showEma9 = !showEma9 },
                       label = { Text("EMA9", color = ChartColors.EMA9) })
            FilterChip(selected = showBb, onClick = { showBb = !showBb },
                       label = { Text("BB", color = ChartColors.BB) })
            FilterChip(selected = showRsi, onClick = { showRsi = !showRsi },
                       label = { Text("RSI", color = MaterialTheme.colorScheme.primary) })
        }
        Spacer(Modifier.height(8.dp))

        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.padding(vertical = 10.dp, horizontal = 6.dp)) {
                when {
                    candleState.loading -> Box(
                        Modifier.fillMaxWidth().height(240.dp),
                        contentAlignment = Alignment.Center,
                    ) { CircularProgressIndicator() }

                    candleState.candles.isEmpty() -> Box(
                        Modifier.fillMaxWidth().height(240.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                candleState.error ?: "No candles for this timeframe yet.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodyMedium,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                modifier = Modifier.padding(horizontal = 16.dp),
                            )
                            Spacer(Modifier.height(10.dp))
                            androidx.compose.material3.TextButton(onClick = onRetryCandles) {
                                Text("Retry")
                            }
                        }
                    }

                    else -> {
                        val cs = candleState.candles
                        KiteStyleChart(
                            candles = cs,
                            showSma20 = showSma,
                            showEma9 = showEma9,
                            showBb = showBb,
                            showRsi = showRsi,
                            sma20Values = CandleChartMath.sma(cs, 20),
                            ema9Values = CandleChartMath.ema(cs, 9),
                            bbUpper = if (showBb) CandleChartMath.bollinger(cs).upper else null,
                            bbLower = if (showBb) CandleChartMath.bollinger(cs).lower else null,
                            rsiValues = if (showRsi) CandleChartMath.rsi(cs) else null,
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // --- Signal statistics ---
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(16.dp)) {
                Text("BOF signal history", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.height(12.dp))
                if (!detail.stats.hasAny) {
                    Text(
                        "No signals yet â€” the BOF engine goes live in Phase 3.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    StatsGrid(detail)
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // --- Reference facts ---
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                FactRow("Currency", detail.currency)
                detail.tickSize?.let { FactRow("Tick size", it.toString()) }
                detail.lotSize?.let { FactRow("Lot size", it.toString()) }
                FactRow("Instrument ID", detail.id.take(8) + "â€¦")
            }
        }
    }
}

@Composable
private fun StatsGrid(detail: InstrumentDetail) {
    val s = detail.stats
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Stat("Total", s.totalSignals)
        Stat("Bullish", s.bullish)
        Stat("Bearish", s.bearish)
    }
    Spacer(Modifier.height(8.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Stat("Confirmed", s.confirmed)
        Stat("Invalidated", s.invalidated)
        Spacer(Modifier.weight(1f))
    }
}

@Composable
private fun Stat(label: String, value: Int) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun FactRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}








