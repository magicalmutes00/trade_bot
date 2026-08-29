package com.bofedge.feature.instrument.presentation

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.OpenInFull
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.bofedge.core.ui.components.EmptyState
import com.bofedge.domain.model.Candle
import com.bofedge.domain.model.CandlestickPattern
import com.bofedge.domain.model.ChartPattern
import com.bofedge.domain.model.InstrumentDetail
import com.bofedge.domain.model.MarketStructure
import com.bofedge.domain.model.PatternDirection
import com.bofedge.domain.model.RiskRewardEngine
import com.bofedge.domain.model.RiskRewardResult
import com.bofedge.domain.model.Timeframe
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.result.ApiResult
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import com.bofedge.feature.instrument.chart.CandleChartMath
import com.bofedge.feature.instrument.chart.KiteStyleChart
import com.bofedge.feature.instrument.chart.TradingViewChartWebView

// ═══════════════════════════════════════════════════════════════════════
//  ViewModel
// ════════════════════════════════════════════════════════════════════════

sealed class InstrumentDetailUiState {
    data object Loading : InstrumentDetailUiState()
    data class Ready(val detail: InstrumentDetail) : InstrumentDetailUiState()
    data class Error(val message: String) : InstrumentDetailUiState()
}

data class CandlesUiState(
    val loading: Boolean = false,
    val timeframe: Timeframe = Timeframe.DAILY,
    val candles: List<Candle> = emptyList(),
    val error: String? = null,
)

data class InstrumentDetailState(
    val uiState: InstrumentDetailUiState = InstrumentDetailUiState.Loading,
    val candles: CandlesUiState = CandlesUiState(),
    val marketStructure: MarketStructure? = null,
    val candlestickPatterns: List<CandlestickPattern>? = null,
    val chartPattern: ChartPattern? = null,
    val riskReward: RiskRewardResult? = null,
)

// ════════════════════════════════════════════════════════════════════════

@HiltViewModel
class InstrumentDetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val repository: InstrumentRepository,
) : ViewModel() {

    val instrumentId: String =
        checkNotNull(savedStateHandle["instrumentId"])

    private val _state =
        MutableStateFlow<InstrumentDetailUiState>(InstrumentDetailUiState.Loading)
    val state: StateFlow<InstrumentDetailUiState> = _state.asStateFlow()

    private val _candles = MutableStateFlow(CandlesUiState(loading = true))
    val candles: StateFlow<CandlesUiState> = _candles.asStateFlow()

    // New state for analysis engines
    private val _marketStructure = MutableStateFlow<MarketStructure?>(null)
    val marketState: StateFlow<MarketStructure?> = _marketStructure.asStateFlow()

    private val _candlestickPatterns = MutableStateFlow<List<CandlestickPattern>?>(null)
    val candlestickPatternState: StateFlow<List<CandlestickPattern>?> = _candlestickPatterns.asStateFlow()

    private val _chartPatterns = MutableStateFlow<List<ChartPattern>?>(null)
    val chartPatternState: StateFlow<List<ChartPattern>?> = _chartPatterns.asStateFlow()

    private val _riskReward = MutableStateFlow<RiskRewardResult?>(null)
    val riskRewardState: StateFlow<RiskRewardResult?> = _riskReward.asStateFlow()

    init {
        load()
        loadCandles()
        viewModelScope.launch { loadAllAnalysis() }
    }

    private fun loadAllAnalysis() = viewModelScope.launch {
        when (val ms = repository.marketStructure(instrumentId, _candles.value.timeframe)) {
            is ApiResult.Success -> _marketStructure.value = ms.value
            else -> {}
        }
        when (val cp = repository.candlestickPatterns(instrumentId, _candles.value.timeframe)) {
            is ApiResult.Success -> _candlestickPatterns.value = cp.value
            else -> {}
        }
        when (val cp = repository.chartPatterns(instrumentId, _candles.value.timeframe)) {
            is ApiResult.Success -> _chartPatterns.value = cp.value
            else -> {}
        }
    }

    fun load() {
        viewModelScope.launch {
            _state.value = InstrumentDetailUiState.Loading
            _state.value = when (val result = repository.detail(instrumentId)) {
                is ApiResult.Success -> InstrumentDetailUiState.Ready(result.value)
                is ApiResult.HttpError ->
                    InstrumentDetailUiState.Error(result.message.ifBlank { "Server error" })
                ApiResult.Offline ->
                    InstrumentDetailUiState.Error("You appear to be offline.")
            }
        }
    }

    fun onTimeframeChange(timeframe: Timeframe) {
        if (_candles.value.timeframe == timeframe) return
        _candles.value = CandlesUiState(timeframe = timeframe, loading = true)
        loadCandlesInternal()
        viewModelScope.launch { loadAllAnalysis() }
    }

    fun loadCandles() = loadCandlesInternal()

    private fun loadCandlesInternal() {
        viewModelScope.launch {
            _candles.value = _candles.value.copy(loading = true, error = null)
            when (val r = repository.candles(instrumentId, _candles.value.timeframe)) {
                is ApiResult.Success -> _candles.value = CandlesUiState(
                    timeframe = _candles.value.timeframe,
                    candles = r.value,
                    loading = false,
                )
                is ApiResult.HttpError -> _candles.value = CandlesUiState(
                    loading = false,
                    error = r.message.ifBlank { "Server error" },
                )
                ApiResult.Offline -> _candles.value = CandlesUiState(
                    loading = false,
                    error = "You appear to be offline.",
                )
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════
//  Route — exposes fullscreen navigation callback
// ═══════════════════════════════════════════════════════════════════════

@Composable
fun InstrumentDetailRoute(
    onOpenFullscreen: (String, String) -> Unit = { _, _ -> },
    viewModel: InstrumentDetailViewModel,
) {
    val detailState by viewModel.state.collectAsStateWithLifecycle()
    val candleState by viewModel.candles.collectAsStateWithLifecycle()
    val marketState by viewModel.marketState.collectAsStateWithLifecycle()
    val cpatternState by viewModel.candlestickPatternState.collectAsStateWithLifecycle()
    val chartState by viewModel.chartPatternState.collectAsStateWithLifecycle()
    val rrState by viewModel.riskRewardState.collectAsStateWithLifecycle()

    val symbol = (detailState as? InstrumentDetailUiState.Ready)?.detail?.symbol ?: ""

    when (val s = detailState) {
        InstrumentDetailUiState.Loading ->
            Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }

        is InstrumentDetailUiState.Error -> EmptyState(
            title = "Couldn't load instrument",
            description = s.message,
            actionLabel = "Retry",
            onAction = viewModel::load,
        )

        is InstrumentDetailUiState.Ready -> InstrumentDetailContent(
            detail = s.detail,
            candleState = candleState,
            marketState = marketState,
            cpatternState = cpatternState,
            chartState = chartState,
            rrState = rrState,
            onTimeframeChange = viewModel::onTimeframeChange,
            onRetryCandles = viewModel::loadCandles,
            onOpenFullscreen = { onOpenFullscreen(viewModel.instrumentId, symbol) },
        )
    }
}

// ═══════════════════════════════════════════════════════════════════════
//  Content
// ═══════════════════════════════════════════════════════════════════════

private val TIMEFRAMES = listOf(Timeframe.DAILY, Timeframe.WEEKLY, Timeframe.MONTHLY)

@Composable
private fun InstrumentDetailContent(
    detail: InstrumentDetail,
    candleState: CandlesUiState,
    marketState: MarketStructure?,
    cpatternState: List<CandlestickPattern>?,
    chartState: List<ChartPattern>?,
    rrState: RiskRewardResult?,
    onTimeframeChange: (Timeframe) -> Unit,
    onRetryCandles: () -> Unit,
    onOpenFullscreen: () -> Unit,
) {
    var selectedTf by rememberSaveable { mutableStateOf(candleState.timeframe) }
    var showSma20 by rememberSaveable { mutableStateOf(false) }
    var showEma9 by rememberSaveable { mutableStateOf(false) }
    var showBb by rememberSaveable { mutableStateOf(false) }
    var showRsi by rememberSaveable { mutableStateOf(false) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
    ) {
        // ── Header ──
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
            Text(detail.symbol, style = MaterialTheme.typography.headlineMedium)
            Text(detail.name,
                 style = MaterialTheme.typography.bodyMedium,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                AssistChip(onClick = {}, enabled = false,
                    label = { Text(detail.exchange) })
                AssistChip(onClick = {}, enabled = false,
                    label = { Text(detail.type.lowercase()) })
                detail.sectorName?.let {
                    AssistChip(onClick = {}, enabled = false,
                        label = { Text(it, maxLines = 1) })
                }
            }
        }

        // ── Price ──
        Card(colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface),
            modifier = Modifier.padding(horizontal = 16.dp).fillMaxWidth(),
        ) {
            Box(Modifier.fillMaxWidth().padding(16.dp), Alignment.Center) {
                val q = detail.quote
                if (q?.lastPrice != null) {
                    Text("₹%.2f".format(q.lastPrice),
                         style = MaterialTheme.typography.headlineMedium,
                         fontWeight = FontWeight.Bold)
                } else {
                    Text("Live quotes arrive with real-time provider",
                         style = MaterialTheme.typography.bodyMedium,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }

        Spacer(Modifier.height(12.dp))

        // ── Timeframes ──
        Row(Modifier.padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            TIMEFRAMES.forEach { tf ->
                FilterChip(selected = selectedTf == tf,
                    onClick = { selectedTf = tf; onTimeframeChange(tf) },
                    label = { Text(tf.code) })
            }
        }

        Spacer(Modifier.height(6.dp))

        // ── Indicators + fullscreen button ──
        Row(Modifier.padding(horizontal = 16.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically) {
            FilterChip(showSma20, { showSma20 = !showSma20 },
                label = { Text("MA20") })
            FilterChip(showEma9, { showEma9 = !showEma9 },
                label = { Text("EMA9") })
            FilterChip(showBb, { showBb = !showBb }, label = { Text("BB") })
            FilterChip(showRsi, { showRsi = !showRsi }, label = { Text("RSI") })
            Spacer(Modifier.weight(1f))
            IconButton(onClick = onOpenFullscreen, Modifier.size(28.dp)) {
                Icon(Icons.Filled.OpenInFull, "Fullscreen",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(18.dp))
            }
        }

        Spacer(Modifier.height(6.dp))

        // ── Chart card ──
        Card(colors = CardDefaults.cardColors(
             containerColor = MaterialTheme.colorScheme.surface),
         modifier = Modifier.padding(horizontal = 16.dp).fillMaxWidth()) {
            Column(Modifier.padding(vertical = 10.dp, horizontal = 6.dp)) {
                when {
                    candleState.loading -> Box(
                        Modifier.fillMaxWidth().height(240.dp), Alignment.Center) {
                        CircularProgressIndicator()
                    }
                    candleState.candles.isEmpty() -> Box(
                        Modifier.fillMaxWidth().height(240.dp), Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(candleState.error ?: "No candles for this timeframe yet.",
                                 style = MaterialTheme.typography.bodyMedium,
                                 color = MaterialTheme.colorScheme.onSurfaceVariant,
                                 textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                 modifier = Modifier.padding(horizontal = 16.dp))
                            Spacer(Modifier.height(10.dp))
                            TextButton(onClick = onRetryCandles) { Text("Retry") }
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
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(12.dp))

        // ── Market Structure ──
        if (marketState != null) {
            Surface(
                shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.5f),
                border = androidx.compose.foundation.BorderStroke(
                    1.dp, MaterialTheme.colorScheme.outline),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("Market Structure", style = MaterialTheme.typography.titleSmall)
                    Text("Trend: ${marketState.trend.name.toLowerCase()}",
                        style = MaterialTheme.typography.bodyMedium)
                    Text("Confidence: ${"%.1f".format(marketState.confidence * 100)}%",
                        style = MaterialTheme.typography.labelSmall)
                    if (marketState.supportResistance.nearestSupport != null) {
                        Text("Support: ${"%.2f".format(marketState.supportResistance.nearestSupport)}",
                            style = MaterialTheme.typography.labelSmall)
                    }
                    if (marketState.supportResistance.nearestResistance != null) {
                        Text("Resistance: ${"%.2f".format(marketState.supportResistance.nearestResistance)}",
                            style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }

        // ── Detected Patterns ──
        if (cpatternState != null && cpatternState.isNotEmpty()) {
            Surface(
                shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.5f),
                border = androidx.compose.foundation.BorderStroke(
                    1.dp, MaterialTheme.colorScheme.outline),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("Candlestick Patterns", style = MaterialTheme.typography.titleSmall)
                    cpatternState.forEach { pattern ->
                        val dir = when (pattern.direction) {
                            PatternDirection.BULLISH -> "Bullish"
                            PatternDirection.BEARISH -> "Bearish"
                            else -> "Neutral"
                        }
                        Text("${pattern.pattern.name.replace("_", " ")} — $dir (${"%.0f".format(pattern.confidence * 100)}%)",
                            style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }

// ── Chart Patterns ──
        if (chartState != null && chartState.isNotEmpty()) {
            Surface(
                shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.5f),
                border = androidx.compose.foundation.BorderStroke(
                    1.dp, MaterialTheme.colorScheme.outline),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("Chart Patterns", style = MaterialTheme.typography.titleSmall)
                    chartState.forEach { cp ->
                        Text("${cp.name.name.replace("_", " ")} — ${cp.direction.name} (${"%.0f".format(cp.confidence * 100)}%)",
                            style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }

        // ── Risk / Reward ──
        if (rrState != null) {
            Surface(
                shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.5f),
                border = androidx.compose.foundation.BorderStroke(
                    1.dp, MaterialTheme.colorScheme.outline),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("Risk / Reward", style = MaterialTheme.typography.titleSmall)
                    Text("Entry: ${"%.2f".format(rrState.entry)}",
                        style = MaterialTheme.typography.labelSmall)
                    Text("Stop Loss: ${"%.2f".format(rrState.stopLoss)}",
                        style = MaterialTheme.typography.labelSmall)
                    Text("Target: ${"%.2f".format(rrState.target)}",
                        style = MaterialTheme.typography.labelSmall)
                    Text("Risk: ${"%.2f".format(rrState.risk)}",
                        style = MaterialTheme.typography.labelSmall)
                    Text("Reward: ${"%.2f".format(rrState.reward)}",
                        style = MaterialTheme.typography.labelSmall)
                    Text("R:R ${RiskRewardEngine.formatRatio(rrState.riskRewardRatio)}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary)
                }
            }
        }

        Spacer(Modifier.height(80.dp)) // bottom padding for nav bar clearance
    }
}

@Composable
private fun StatCell(label: String, value: Int) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text("$value", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelSmall,
             color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}