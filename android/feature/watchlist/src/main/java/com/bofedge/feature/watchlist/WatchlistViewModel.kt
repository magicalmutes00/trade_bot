package com.bofedge.feature.watchlist.presentation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.domain.model.Watchlist
import com.bofedge.domain.repository.WatchlistRepository
import com.bofedge.domain.result.ApiResult
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class WatchlistUiState(
    val loading: Boolean = false,
    val lists: List<Watchlist> = emptyList(),
    val selectedId: String? = null,
    val error: String? = null,
    val showCreateDialog: Boolean = false,
    val newName: String = "",
)

@HiltViewModel
class WatchlistViewModel @Inject constructor(
    private val repository: WatchlistRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(WatchlistUiState(loading = true))
    val state: StateFlow<WatchlistUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            when (val result = repository.list()) {
                is ApiResult.Success -> _state.update { s ->
                    s.copy(
                        loading = false,
                        lists = result.value,
                        selectedId = s.selectedId ?: result.value.firstOrNull()?.id,
                    )
                }
                is ApiResult.HttpError ->
                    _state.update { it.copy(loading = false, error = result.message.ifBlank { "Server error" }) }
                ApiResult.Offline ->
                    _state.update { it.copy(loading = false, error = "You appear to be offline.") }
            }
        }
    }

    fun select(id: String?) = _state.update { it.copy(selectedId = id) }

    // ------------------------------------------------------------- create

    fun startCreate() = _state.update { it.copy(showCreateDialog = true, newName = "") }
    fun dismissCreate() = _state.update { it.copy(showCreateDialog = false) }
    fun onNameChange(name: String) = _state.update { it.copy(newName = name) }

    fun confirmCreate() {
        val name = _state.value.newName.trim()
        if (name.isEmpty()) return
        viewModelScope.launch {
            when (val r = repository.create(name)) {
                is ApiResult.Success -> {
                    dismissCreate()
                    refresh(selectId = r.value.id)
                }
                else -> _state.update { it.copy(error = messageOf(r)) }
            }
        }
    }

    fun deleteSelected() {
        val id = _state.value.selectedId ?: return
        viewModelScope.launch {
            repository.delete(id)
            _state.update { it.copy(selectedId = null) }
            refresh()
        }
    }

    // -------------------------------------------------------------- items

    fun toggleAlert(instrumentId: String, enabled: Boolean) {
        val wlId = _state.value.selectedId ?: return
        viewModelScope.launch {
            when (val r = repository.setAlert(wlId, instrumentId, enabled)) {
                is ApiResult.Success -> replace(r.value)
                else -> _state.update { it.copy(error = messageOf(r)) }
            }
        }
    }

    fun removeItem(instrumentId: String) {
        val wlId = _state.value.selectedId ?: return
        viewModelScope.launch {
            repository.removeItem(wlId, instrumentId)
            refresh()
        }
    }

    /** Used by the Scanner's add-to-watchlist picker. */
    fun addToWatchlist(watchlistId: String, instrumentId: String, onDone: (Boolean) -> Unit) {
        viewModelScope.launch {
            when (repository.addItem(watchlistId, instrumentId)) {
                is ApiResult.Success -> onDone(true)
                else -> onDone(false)
            }
        }
    }

    // ------------------------------------------------------------ helpers

    private suspend fun refresh(selectId: String? = null) {
        when (val r = repository.list()) {
            is ApiResult.Success -> _state.update { s ->
                s.copy(
                    lists = r.value,
                    selectedId = selectId ?: s.selectedId?.takeIf { id ->
                        r.value.any { w -> w.id == id }
                    } ?: r.value.firstOrNull()?.id,
                    error = null,
                )
            }
            else -> _state.update { it.copy(error = messageOf(r)) }
        }
    }

    private suspend fun replace(updated: Watchlist) {
        _state.update { s ->
            s.copy(lists = s.lists.map { w -> if (w.id == updated.id) updated else w })
        }
    }

    private fun messageOf(r: ApiResult<*>): String = when (r) {
        is ApiResult.HttpError -> r.message.ifBlank { "Server error" }
        ApiResult.Offline -> "You appear to be offline."
        else -> "Something went wrong"
    }
}

