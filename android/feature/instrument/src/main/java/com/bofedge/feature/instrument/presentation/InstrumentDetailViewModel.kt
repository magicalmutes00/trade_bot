package com.bofedge.feature.instrument.presentation

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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

@HiltViewModel
class InstrumentDetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val repository: InstrumentRepository,
) : ViewModel() {

    private val instrumentId: String = checkNotNull(savedStateHandle["instrumentId"])

    private val _state =
        MutableStateFlow<InstrumentDetailUiState>(InstrumentDetailUiState.Loading)
    val state: StateFlow<InstrumentDetailUiState> = _state.asStateFlow()

    init {
        load()
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
}
