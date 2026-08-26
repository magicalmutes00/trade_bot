package com.bofedge.feature.instrument.presentation

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
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
import com.bofedge.feature.instrument.chart.TradingViewChartWebView

/** Every interval the backend serves (backend Timeframe enum). */
private val CHART_TIMEFRAMES = listOf("1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W")

@Composable
fun FullscreenChartScreen(
    viewModel: InstrumentDetailViewModel,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val activity = context as? Activity

    val detailState by viewModel.state.collectAsStateWithLifecycle()
    val candleState by viewModel.candles.collectAsStateWithLifecycle()

    var showSma20 by remember { mutableStateOf(true) }
    var showEma9 by remember { mutableStateOf(false) }
    var showBb by remember { mutableStateOf(false) }
    var showRsi by remember { mutableStateOf(false) }
    var useTradingView by rememberSaveable { mutableStateOf(false) }

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
            Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onClose) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = Color(0xFFEAF0F6))
            }

            when (val s = detailState) {
                is InstrumentDetailUiState.Ready -> {
                    Column(Modifier.weight(1f)) {
                        Text(s.detail.symbol, fontWeight = FontWeight.Bold,
                             color = Color(0xFFEAF0F6))
                        s.detail.quote?.lastPrice?.let {
                            Text("₹%.2f".format(it), color = Color(0xFF16C784),
                                 style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
                else -> Text("Loading…", color = Color(0xFF8A97A8),
                             modifier = Modifier.weight(1f))
            }

            ChartDropdown(
                label = candleState.timeframe,
                items = CHART_TIMEFRAMES,
                selectedItem = candleState.timeframe,
                itemLabel = { it },
                isSelected = { it == candleState.timeframe },
                onSelect = { tf -> viewModel.onTimeframeChange(tf) },
            )

            ChartDropdown(
                label = indicatorsLabel(showSma20, showEma9, showBb, showRsi),
                items = listOf("MA20", "EMA9", "BB", "RSI"),
                selectedItem = null,
                itemLabel = { it },
                isSelected = { ind -> isIndicatorOn(ind, showSma20, showEma9, showBb, showRsi) },
                onSelect = { ind ->
                    when (ind) {
                        "MA20" -> showSma20 = !showSma20
                        "EMA9" -> showEma9 = !showEma9
                        "BB" -> showBb = !showBb
                        "RSI" -> showRsi = !showRsi
                    }
                },
                modifier = Modifier.padding(start = 4.dp),
            )
        }

        // ---- Renderer toggle ----
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            RendererChip("Native", !useTradingView) { useTradingView = false }
            RendererChip("TradingView", useTradingView) { useTradingView = true }        }

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
                    if (useTradingView) {
                        TradingViewChartWebView(
                            candles = cs,
                            showSma20 = showSma20,
                            showEma9 = showEma9,
                            showBb = showBb,
                            showRsi = showRsi,
                            modifier = Modifier.fillMaxSize(),
                        )
                    } else {
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
        }

        Spacer(Modifier.height(4.dp))
    }
}

@Composable
private fun <T> ChartDropdown(
    label: String,
    items: List<T>,
    selectedItem: T?,
    itemLabel: (T) -> String,
    isSelected: (T) -> Boolean,
    onSelect: (T) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }

    Box(modifier) {
        TextButton(
            onClick = { expanded = true },
            colors = ButtonDefaults.textButtonColors(contentColor = Color(0xFF8A97A8)),
            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
        ) {
            Text(
                label,
                style = MaterialTheme.typography.labelLarge,
                color = if (selectedItem != null && isSelected(selectedItem)) {
                    Color(0xFF4E9CFF)
                } else {
                    Color(0xFFEAF0F6)
                },
            )
            Icon(Icons.Filled.ArrowDropDown, null, tint = Color(0xFF8A97A8))
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            containerColor = Color(0xFF141B25),
        ) {
            items.forEach { item ->
                val selected = isSelected(item)
                DropdownMenuItem(
                    text = {
                        Text(
                            itemLabel(item),
                            style = MaterialTheme.typography.labelLarge,
                            color = if (selected) Color(0xFF4E9CFF) else Color(0xFFEAF0F6),
                        )
                    },
                    trailingIcon = if (selected) {
                        { Icon(Icons.Filled.Check, null, tint = Color(0xFF4E9CFF)) }
                    } else {
                        null
                    },
                    onClick = {
                        onSelect(item)
                        expanded = false
                    },
                )
            }
        }
    }
}

private fun isIndicatorOn(
    ind: String,
    sma20: Boolean, ema9: Boolean, bb: Boolean, rsi: Boolean,
): Boolean = when (ind) {
    "MA20" -> sma20
    "EMA9" -> ema9
    "BB" -> bb
    "RSI" -> rsi
    else -> false
}

private fun indicatorsLabel(
    sma20: Boolean, ema9: Boolean, bb: Boolean, rsi: Boolean,
): String {
    val on = listOfNotNull(
        "MA20".takeIf { sma20 },
        "EMA9".takeIf { ema9 },
        "BB".takeIf { bb },
        "RSI".takeIf { rsi },
    )
    return when {
        on.isEmpty() -> "Indicators"
        on.size == 1 -> on[0]
        else -> "${on.size} indicators"
    }
}

@Composable
private fun RendererChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        shape = MaterialTheme.shapes.small,
        color = if (selected) Color(0xFF4E9CFF).copy(alpha = .2f) else Color.Transparent,
        border = androidx.compose.foundation.BorderStroke(
            1.dp, if (selected) Color(0xFF4E9CFF) else Color(0xFF232D3D),
        ),
        onClick = onClick,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = if (selected) Color(0xFF4E9CFF) else Color(0xFF8A97A8),
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
        )
    }
}
