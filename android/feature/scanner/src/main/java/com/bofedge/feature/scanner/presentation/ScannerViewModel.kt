package com.bofedge.feature.scanner.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.domain.model.Instrument
import com.bofedge.domain.model.PageResult
import com.bofedge.domain.model.Watchlist
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.repository.InstrumentSort
import com.bofedge.domain.repository.WatchlistRepository
import com.bofedge.domain.result.ApiResult
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

private const val PAGE_SIZE = 25
private const val DEBOUNCE_MS = 350L

@HiltViewModel
class ScannerViewModel @Inject constructor(
    private val repository: InstrumentRepository,
    private val watchlistRepository: WatchlistRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ScannerUiState())
    val state: StateFlow<ScannerUiState> = _state.asStateFlow()

    private var reloadJob: Job? = null

    init {
        refresh()
    }

    // ------------------------------------------- add-to-watchlist (Phase 5)

    fun openWatchlistPicker(instrumentId: String) {
        _state.update { it.copy(showWatchlistPicker = true, pickerInstrumentId = instrumentId, error = null) }
        viewModelScope.launch {
            when (val r = watchlistRepository.list()) {
                is ApiResult.Success -> _state.update { it.copy(watchlists = r.value) }
                else -> _state.update { it.copy(watchlists = emptyList()) }
            }
        }
    }

    fun dismissWatchlistPicker() =
        _state.update { it.copy(showWatchlistPicker = false, watchlists = emptyList()) }

    /** Adds to the chosen list; creates a "Default" list on first use. */
    fun addToWatchlist(watchlistId: String?, instrumentId: String) {
        viewModelScope.launch {
            val targetId = watchlistId ?: run {
                when (val created = watchlistRepository.create("Default")) {
                    is ApiResult.Success -> created.value.id
                    is ApiResult.HttpError ->
                        if (created.code == "CONFLICT") {
                            // exists already — find it
                            val lists = (watchlistRepository.list() as? ApiResult.Success)?.value
                                ?: return@launch
                            lists.first { it.name == "Default" }.id
                        } else return@launch
                    else -> return@launch
                }
            }
            watchlistRepository.addItem(targetId, instrumentId)
            dismissWatchlistPicker()
        }
    }


    fun onQueryChange(query: String) {
        _state.update { it.copy(query = query) }
        reloadJob?.cancel()
        reloadJob = viewModelScope.launch {
            delay(DEBOUNCE_MS)
            refresh()
        }
    }

    fun onTypeFilterChange(type: String?) {
        if (_state.value.typeFilter == type) return
        _state.update { it.copy(typeFilter = type) }
        refresh()
    }

    fun onSortChange(sort: InstrumentSort) {
        if (_state.value.sort == sort) return
        _state.update { it.copy(sort = sort) }
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            applyPage(
                repository.search(
                    query = _state.value.query,
                    type = _state.value.typeFilter,
                    sort = _state.value.sort,
                    limit = PAGE_SIZE,
                    offset = 0,
                ),
                replace = true,
            )
        }
    }

    /** Infinite-scroll continuation; no-ops while a page is in flight. */
    fun loadMore() {
        val s = _state.value
        if (s.loading || s.appending || s.endReached || s.items.isEmpty()) return
        viewModelScope.launch {
            _state.update { it.copy(appending = true) }
            applyPage(
                repository.search(
                    query = s.query,
                    type = s.typeFilter,
                    sort = s.sort,
                    limit = PAGE_SIZE,
                    offset = s.items.size,
                ),
                replace = false,
            )
        }
    }

    private suspend fun applyPage(result: ApiResult<PageResult<Instrument>>, replace: Boolean) {
        when (result) {
            is ApiResult.Success -> {
                val page = result.value
                _state.update { s ->
                    val merged =
                        if (replace) page.items
                        else (s.items + page.items).distinctBy { it.id }
                    s.copy(
                        loading = false,
                        appending = false,
                        items = merged,
                        total = page.total,
                        endReached = merged.size >= page.total || page.items.isEmpty(),
                        error = null,
                    )
                }
            }
            is ApiResult.HttpError ->
                _state.update {
                    it.copy(loading = false, appending = false, error = result.message.ifBlank { "Server error" })
                }
            ApiResult.Offline ->
                _state.update {
                    it.copy(loading = false, appending = false, error = "You appear to be offline.")
                }
        }
    }
}



