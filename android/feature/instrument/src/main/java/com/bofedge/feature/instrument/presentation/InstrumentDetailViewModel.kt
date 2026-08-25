package com.bofedge.feature.instrument.presentation

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.domain.model.Candle
import com.bofedge.domain.model.InstrumentDetail
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.result.ApiResult
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class InstrumentDetailUiState {
    object Loading : InstrumentDetailUiState()
    data class Ready(val detail: InstrumentDetail) : InstrumentDetailUiState()
    data class Error(val message: String) : InstrumentDetailUiState()
}

/** Candles for the currently selected timeframe. */
data class CandlesUiState(
    val loading: Boolean = false,
    val timeframe: String = "15m",
    val candles: List<Candle> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class InstrumentDetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val repository: InstrumentRepository,
) : ViewModel() {

    private val instrumentId: String = checkNotNull(savedStateHandle["instrumentId"])

    private val _state =
        MutableStateFlow<InstrumentDetailUiState>(InstrumentDetailUiState.Loading)
    val state: StateFlow<InstrumentDetailUiState> = _state.asStateFlow()

    private val _candles = MutableStateFlow(CandlesUiState(loading = true))
    val candles: StateFlow<CandlesUiState> = _candles.asStateFlow()

    init {
        load()
        loadCandles()
    }

    fun load() {
        viewModelScope.launch {
            _state.value = InstrumentDetailUiState.Loading
            _state.value = when (val result = repository.detail(instrumentId)) {
                is ApiResult.Success -> InstrumentDetailUiState.Ready(result.value)
                is ApiResult.HttpError ->
                    InstrumentDetailUiState.Error(result.message.ifBlank { "Server error" })
                ApiResult.Offline -> InstrumentDetailUiState.Error("You appear to be offline.")
            }
        }
    }

    // ------------------------------------------------------------------ candles

    fun onTimeframeChange(timeframe: String) {
        if (_candles.value.timeframe == timeframe) return
        _candles.value = CandlesUiState(timeframe = timeframe, loading = true)
        loadCandles()
    }

    fun loadCandles() {
        viewModelScope.launch {
            _candles.update { it.copy(loading = true, error = null) }
            when (
                val result = repository.candles(instrumentId, _candles.value.timeframe)
            ) {
                is ApiResult.Success -> _candles.value = _candles.value.copy(
                    loading = false,
                    candles = result.value,
                    error = if (result.value.isEmpty()) "No candles for this timeframe yet." else null,
                )
                is ApiResult.HttpError -> _candles.value = _candles.value.copy(
                    loading = false,
                    error = result.message.ifBlank { "Server error" },
                )
                ApiResult.Offline -> _candles.value = _candles.value.copy(
                    loading = false,
                    error = "You appear to be offline.",
                )
            }
        }
    }
}

private inline fun <T> MutableStateFlow<T>.update(update: (T) -> T) {
    value = update(value)
}
