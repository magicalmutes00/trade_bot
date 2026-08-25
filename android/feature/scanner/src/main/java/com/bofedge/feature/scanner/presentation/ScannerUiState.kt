package com.bofedge.feature.scanner.presentation

import com.bofedge.domain.model.Instrument
import com.bofedge.domain.model.Watchlist
import com.bofedge.domain.repository.InstrumentSort

/**
 * Scanner UI state. `items` holds one accumulated page stream; the backend
 * paginates (limit/offset) so thousands of symbols never sit in memory.
 */
data class ScannerUiState(
    val loading: Boolean = false,
    val appending: Boolean = false,
    val items: List<Instrument> = emptyList(),
    val total: Int = 0,
    val endReached: Boolean = false,
    val query: String = "",
    val typeFilter: String? = null, // null = ALL
    val sort: InstrumentSort = InstrumentSort.SYMBOL,
    val error: String? = null,
    // Phase 5 — add-to-watchlist picker
    val showWatchlistPicker: Boolean = false,
    val watchlists: List<Watchlist> = emptyList(),
    val pickerInstrumentId: String? = null,
) {
    val showInitialError: Boolean get() = error != null && items.isEmpty()
}
