package com.bofedge.feature.instrument.presentation

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.bofedge.feature.instrument.chart.CandleChartMath
import com.bofedge.feature.instrument.chart.KiteStyleChart

private val FS_TIMEFRAMES = listOf("15m", "1h", "4h", "1D")

@Composable
fun FullscreenChartScreen(viewModel: InstrumentDetailViewModel) {
    val context = LocalContext.current
    val activity = context as? Activity

    val detailState by viewModel.state.collectAsStateWithLifecycle()
    val candleState by viewModel.candles.collectAsStateWithLifecycle()

    var showSma20 by remember { mutableStateOf(true) }
    var showEma9 by remember { mutableStateOf(false) }
    var showBb by remember { mutableStateOf(false) }
    var showRsi by remember { mutableStateOf(false) }

    // Hide system bars
    LaunchedEffect(Unit) {
        activity?.window?.let { window ->
            val ctrl = WindowCompat.getInsetsController(window, window.decorView)
            ctrl.systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            ctrl.hide(WindowInsetsCompat.Type.systemBars())
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            activity?.window?.let { window ->
                WindowCompat.getInsetsController(window, window.decorView)
                    .show(WindowInsetsCompat.Type.systemBars())
            }
        }
    }

    Column(
        Modifier.fillMaxSize().background(Color(0xFF0B0F14)),
    ) {
        // ---- Top bar ----
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            when (val s = detailState) {
                is InstrumentDetailUiState.Ready -> {
                    Column {
                        Text(s.detail.symbol, fontWeight = FontWeight.Bold,
                             color = Color(0xFFEAF0F6))
                        s.detail.quote?.lastPrice?.let {
                            Text("₹%.2f".format(it), color = Color(0xFF16C784),
                                 style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
                else -> Text("Loading…", color = Color(0xFF8A97A8))
            }

            IconButton(onClick = { activity?.finish() }) {
                Icon(Icons.Filled.Close, "Close", tint = Color(0xFFEAF0F6))
            }
        }

        // ---- Timeframe chips ----
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            FS_TIMEFRAMES.forEach { tf ->
                FilterChip(
                    selected = candleState.timeframe == tf,
                    onClick = { viewModel.onTimeframeChange(tf) },
                    label = { Text(tf, style = MaterialTheme.typography.labelSmall) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = Color(0xFF4E9CFF).copy(alpha = .2f),
                        selectedLabelColor = Color(0xFF4E9CFF),
                    ),
                )
            }
        }

        Spacer(Modifier.height(6.dp))

        // ---- Indicator chips (scrollable row) ----
        Row(
            Modifier.fillMaxWidth()
                .padding(horizontal = 12.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            IndicatorChip("MA20", showSma20) { showSma20 = !showSma20 }
            IndicatorChip("EMA9", showEma9) { showEma9 = !showEma9 }
            IndicatorChip("BB", showBb) { showBb = !showBb }
            IndicatorChip("RSI", showRsi) { showRsi = !showRsi }
        }

        Spacer(Modifier.height(4.dp))

        // ---- Chart fills remaining space ----
        Box(Modifier.weight(1f)) {
            when {
                candleState.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) {
                    CircularProgressIndicator(color = Color(0xFF4E9CFF))
                }
                candleState.candles.isEmpty() -> Box(
                    Modifier.fillMaxSize(), Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(candleState.error ?: "No data", color = Color(0xFF8A97A8))
                        Spacer(Modifier.height(8.dp))
                        TextButton(onClick = viewModel::loadCandles) { Text("Retry") }
                    }
                }
                else -> {
                    val cs = candleState.candles
                    KiteStyleChart(
                        candles = cs,
                        showSma20 = showSma20,
                        showEma9 = showEma9,
                        showBb = showBb,
                        showRsi = showRsi,
                        sma20Values = CandleChartMath.sma(cs, 20),
                        ema9Values = CandleChartMath.ema(cs, 9),
                        bbUpper = if (showBb) CandleChartMath.bollinger(cs).upper else null,
                        bbLower = if (showBb) CandleChartMath.bollinger(cs).lower else null,
                        rsiValues = if (showRsi) CandleChartMath.rsi(cs) else null,
                        modifier = Modifier.fillMaxSize(),
                    )
                }
            }
        }

        Spacer(Modifier.height(4.dp))
    }
}

@Composable
private fun IndicatorChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        shape = MaterialTheme.shapes.small,
        color = if (selected) Color(0xFF4E9CFF).copy(alpha = .2f) else Color.Transparent,
        border = androidx.compose.foundation.BorderStroke(
            1.dp, if (selected) Color(0xFF4E9CFF) else Color(0xFF232D3D),
        ),
        modifier = Modifier.clickable(onClick = onClick),
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = if (selected) Color(0xFF4E9CFF) else Color(0xFF8A97A8),
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
        )
    }
}
