package com.bofedge.feature.heatmap.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.data.network.MarketSocketClient
import com.bofedge.data.network.WsEvent
import com.bofedge.domain.model.HeatmapGroup
import com.bofedge.domain.model.QuoteTick
import com.bofedge.domain.model.RealtimeConnection
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.result.ApiResult
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class HeatmapUiState(
    val loading: Boolean = false,
    val groups: List<HeatmapGroup> = emptyList(),
    val groupBySector: Boolean = true,
    val onlyWithSignals: Boolean = false,
    val error: String? = null,
    /** Live ticks merged over cell prices, keyed by symbol (from /ws/market). */
    val liveTicks: Map<String, QuoteTick> = emptyMap(),
    val connection: RealtimeConnection = RealtimeConnection.OFFLINE,
)

@HiltViewModel
class HeatmapViewModel @Inject constructor(
    private val repository: InstrumentRepository,
    private val socket: MarketSocketClient,
) : ViewModel() {

    private val _state = MutableStateFlow(HeatmapUiState(loading = true))
    val state: StateFlow<HeatmapUiState> = _state.asStateFlow()

    init {
        refresh()
        socket.connect()
        viewModelScope.launch {
            socket.events.collect { event ->
                when (event) {
                    is WsEvent.Quotes -> _state.update { s ->
                        val merged = s.liveTicks.toMutableMap()
                        event.ticks.forEach { t -> merged[t.symbol] = t }
                        s.copy(liveTicks = merged)
                    }
                    WsEvent.Live -> _state.update {
                        it.copy(connection = RealtimeConnection.LIVE)
                    }
                    is WsEvent.Reconnecting -> _state.update {
                        it.copy(connection = RealtimeConnection.RECONNECTING)
                    }
                    else -> Unit
                }
            }
        }
    }

    fun toggleGrouping() {
        _state.update { it.copy(groupBySector = !it.groupBySector) }
        refresh()
    }

    fun toggleOnlySignals() {
        _state.update { it.copy(onlyWithSignals = !it.onlyWithSignals) }
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            when (
                val result = repository.heatmap(
                    groupBy = if (_state.value.groupBySector) "sector" else "type",
                    onlyWithSignals = _state.value.onlyWithSignals,
                )
            ) {
                is ApiResult.Success ->
                    _state.update { it.copy(loading = false, groups = result.value) }
                is ApiResult.HttpError ->
                    _state.update { it.copy(loading = false, error = result.message.ifBlank { "Server error" }) }
                ApiResult.Offline ->
                    _state.update { it.copy(loading = false, error = "You appear to be offline.") }
            }
        }
    }

    override fun onCleared() {
        socket.disconnect()
        super.onCleared()
    }
}
