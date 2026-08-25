package com.bofedge.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bofedge.domain.model.AuthUser
import com.bofedge.domain.model.DashboardSnapshot
import com.bofedge.domain.repository.UserRepository
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.result.ApiResult
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Profile fetch state for the authenticated shell. */
sealed class ProfileUiState {
    object Loading : ProfileUiState()
    data class Ready(val user: AuthUser) : ProfileUiState()
    data class Error(val message: String) : ProfileUiState()
}

sealed class DashboardUiState {
    object Loading : DashboardUiState()
    data class Ready(val snapshot: DashboardSnapshot) : DashboardUiState()
    data class Error(val message: String) : DashboardUiState()
}

/**
 * Shell data: proves the protected-endpoint path (GET /profile with the
 * Firebase token attached by FirebaseAuthInterceptor) and feeds the
 * dashboard tab (market status + BOF summary).
 */
@HiltViewModel
class MainViewModel @Inject constructor(
    private val userRepository: UserRepository,
    private val instrumentRepository: InstrumentRepository,
) : ViewModel() {

    private val _profile = MutableStateFlow<ProfileUiState>(ProfileUiState.Loading)
    val profile: StateFlow<ProfileUiState> = _profile.asStateFlow()

    private val _dashboard = MutableStateFlow<DashboardUiState>(DashboardUiState.Loading)
    val dashboard: StateFlow<DashboardUiState> = _dashboard.asStateFlow()

    init {
        refreshProfile()
        refreshDashboard()
    }

    fun refreshProfile() {
        viewModelScope.launch {
            _profile.value = ProfileUiState.Loading
            _profile.value = when (val result = userRepository.getProfile()) {
                is ApiResult.Success -> ProfileUiState.Ready(result.value)
                is ApiResult.HttpError ->
                    if (result.httpStatus == 401) {
                        ProfileUiState.Error("Session expired. Please sign in again.")
                    } else {
                        ProfileUiState.Error(result.message.ifBlank { "Server error" })
                    }
                ApiResult.Offline -> ProfileUiState.Error("You appear to be offline.")
            }
        }
    }

    fun refreshDashboard() {
        viewModelScope.launch {
            _dashboard.value = DashboardUiState.Loading
            _dashboard.value = when (val result = instrumentRepository.dashboard()) {
                is ApiResult.Success -> DashboardUiState.Ready(result.value)
                is ApiResult.HttpError -> DashboardUiState.Error(result.message.ifBlank { "Server error" })
                ApiResult.Offline -> DashboardUiState.Error("You appear to be offline.")
            }
        }
    }
}
