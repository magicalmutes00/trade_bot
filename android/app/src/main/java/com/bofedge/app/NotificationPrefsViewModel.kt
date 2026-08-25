package com.bofedge.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.domain.model.NotificationPreferences
import com.bofedge.domain.repository.NotificationRepository
import com.bofedge.domain.result.ApiResult
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class NotificationPrefsUiState(
    val loading: Boolean = false,
    val prefs: NotificationPreferences? = null,
    val saving: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class NotificationPrefsViewModel @Inject constructor(
    private val repository: NotificationRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(NotificationPrefsUiState(loading = true))
    val state: StateFlow<NotificationPrefsUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            apply(repository.preferences())
        }
    }

    fun setPushEnabled(value: Boolean) = patch(pushEnabled = value)
    fun setBullish(value: Boolean) = patch(bullishAlerts = value)
    fun setBearish(value: Boolean) = patch(bearishAlerts = value)
    fun setStrongOnly(value: Boolean) = patch(strongOnly = value)
    fun setWatchlistOnly(value: Boolean) = patch(watchlistOnly = value)

    fun cycleMinStrength() {
        val order = listOf("WEAK", "MODERATE", "STRONG", "VERY_STRONG")
        val cur = _state.value.prefs?.minStrength ?: "MODERATE"
        val next = order[(order.indexOf(cur) + 1).coerceAtMost(order.lastIndex)]
        patch(minStrength = next)
    }

    private fun patch(
        pushEnabled: Boolean? = null, bullishAlerts: Boolean? = null,
        bearishAlerts: Boolean? = null, strongOnly: Boolean? = null,
        watchlistOnly: Boolean? = null, minStrength: String? = null,
    ) {
        // optimistic update, server is the source of truth on response
        _state.update { s ->
            s.copy(saving = true, prefs = s.prefs?.copy(
                pushEnabled = pushEnabled ?: s.prefs?.pushEnabled ?: s.prefs?.pushEnabled ?: true,
                bullishAlerts = bullishAlerts ?: s.prefs?.bullishAlerts ?: true,
                bearishAlerts = bearishAlerts ?: s.prefs?.bearishAlerts ?: true,
                strongOnly = strongOnly ?: s.prefs?.strongOnly ?: false,
                watchlistOnly = watchlistOnly ?: s.prefs?.watchlistOnly ?: false,
                minStrength = minStrength ?: s.prefs?.minStrength ?: "MODERATE",
            ))
        }
        viewModelScope.launch {
            apply(repository.updatePreferences(
                pushEnabled = pushEnabled,
                bullishAlerts = bullishAlerts,
                bearishAlerts = bearishAlerts,
                strongOnly = strongOnly,
                watchlistOnly = watchlistOnly,
                minStrength = minStrength,
            ))
        }
    }

    private suspend fun apply(result: ApiResult<NotificationPreferences>) {
        when (result) {
            is ApiResult.Success -> _state.update {
                it.copy(loading = false, saving = false, prefs = result.value, error = null)
            }
            is ApiResult.HttpError -> _state.update {
                it.copy(loading = false, saving = false,
                        error = result.message.ifBlank { "Server error" })
            }
            ApiResult.Offline -> _state.update {
                it.copy(loading = false, saving = false, error = "You appear to be offline.")
            }
        }
    }
}
