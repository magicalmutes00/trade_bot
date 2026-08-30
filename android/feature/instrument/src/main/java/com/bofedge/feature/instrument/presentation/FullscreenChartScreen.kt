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
import com.bofedge.feature.instrument.chart.KiteStyleChart
import com.bofedge.feature.instrument.chart.TradingViewChartWebView
import com.bofedge.feature.instrument.chart.toJsMarkers
import com.bofedge.feature.instrument.chart.toNativeLevels

import com.bofedge.domain.model.InstrumentDetail
import com.bofedge.domain.model.Timeframe
import com.bofedge.feature.instrument.presentation.InstrumentDetailUiState

/** Every interval the backend serves (4h is the spec's primary scan TF). */
private val CHART_TIMEFRAMES = listOf(Timeframe.H4, Timeframe.DAILY, Timeframe.WEEKLY, Timeframe.MONTHLY)

@Composable
fun FullscreenChartScreen(
    viewModel: InstrumentDetailViewModel,
    onClose: () -> Unit,
) {
    val context = LocalContext.current
    val activity = context as? Activity

    val detailState by viewModel.state.collectAsStateWithLifecycle()
    val candleState by viewModel.candles.collectAsStateWithLifecycle()
    val tradePatternState by viewModel.tradePatternState.collectAsStateWithLifecycle()

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

            if (detailState is InstrumentDetailUiState.Ready) {
                val d = detailState as InstrumentDetailUiState.Ready
                Column(Modifier.weight(1f)) {
                    Text(d.detail.symbol, fontWeight = FontWeight.Bold,
                         color = Color(0xFFEAF0F6))
                    d.detail.quote?.lastPrice?.let {
                        Text("₹%.2f".format(it), color = Color(0xFF16C784),
                             style = MaterialTheme.typography.bodyMedium)
                    }
                }
            } else {
                Text("Loading…", color = Color(0xFF8A97A8),
                     modifier = Modifier.weight(1f))
            }

            ChartDropdown(
                label = candleState.timeframe.toString(),
                items = CHART_TIMEFRAMES,
                selectedItem = candleState.timeframe,
                itemLabel = { it.toString() },
                isSelected = { it == candleState.timeframe },
                onSelect = { tf -> viewModel.onTimeframeChange(tf) },
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
                    val patterns = tradePatternState.orEmpty()
                    if (useTradingView) {
                        TradingViewChartWebView(
                            candles = cs,
                            timeframe = candleState.timeframe.toString(),
                            patternNames = patterns.map { it.patternDetected },
                            markers = patterns.toJsMarkers(cs),
                            modifier = Modifier.fillMaxSize(),
                        )
                    } else {
                        KiteStyleChart(
                            candles = cs,
                            levels = patterns.toNativeLevels(),
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
