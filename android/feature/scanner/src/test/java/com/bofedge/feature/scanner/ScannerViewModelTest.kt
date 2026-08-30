package com.bofedge.feature.scanner

import com.bofedge.domain.model.Candle
import com.bofedge.domain.model.Instrument
import com.bofedge.domain.model.PageResult
import com.bofedge.domain.model.Timeframe
import com.bofedge.domain.repository.InstrumentRepository
import com.bofedge.domain.repository.InstrumentSort
import com.bofedge.domain.result.ApiResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

private fun inst(n: Int) = Instrument(
    id = "id-$n", symbol = "SYM$n", name = "Instrument $n",
    type = "STOCK", exchange = "NSE", currency = "INR", sectorName = null,
)

/** Records calls and returns queued pages per (query,type,sort) bucket. */
private class FakeRepo : InstrumentRepository {
    var pages: List<PageResult<Instrument>> = emptyList()
    val searches = mutableListOf<Pair<Int, Int>>() // offset to limit

    override suspend fun search(
        query: String?, type: String?, sort: InstrumentSort, limit: Int, offset: Int,
    ): ApiResult<PageResult<Instrument>> {
        searches += offset to limit
        return ApiResult.Success(pages.getOrElse(offset / limit) { PageResult(emptyList(), 0, offset) })
    }

    override suspend fun detail(id: String): ApiResult<com.bofedge.domain.model.InstrumentDetail> =
        error("not used in scanner tests")

    override suspend fun dashboard(): ApiResult<com.bofedge.domain.model.DashboardSnapshot> =
        error("not used in scanner tests")

    override suspend fun heatmap(
        groupBy: String, type: String?, onlyWithSignals: Boolean,
    ): ApiResult<List<com.bofedge.domain.model.HeatmapGroup>> = error("not used in scanner tests")

    override suspend fun signalStats(id: String): ApiResult<com.bofedge.domain.model.SignalStatsDetailed> =
        error("not used in scanner tests")

    override suspend fun candles(id: String, timeframe: Timeframe, limit: Int): ApiResult<List<com.bofedge.domain.model.Candle>> =
        error("not used in scanner tests")

    override suspend fun candlestickPatterns(
        id: String, timeframe: Timeframe,
    ): ApiResult<List<com.bofedge.domain.model.CandlestickPattern>> = error("not used in scanner tests")

    override suspend fun chartPatterns(
        id: String, timeframe: Timeframe,
    ): ApiResult<List<com.bofedge.domain.model.ChartPattern>> = error("not used in scanner tests")

    override suspend fun marketStructure(
        id: String, timeframe: Timeframe, lookback: Int,
    ): ApiResult<com.bofedge.domain.model.MarketStructure> = error("not used in scanner tests")

    override suspend fun patternSignals(
        id: String, timeframe: Timeframe?,
    ): ApiResult<List<com.bofedge.domain.model.TradePattern>> = error("not used in scanner tests")
}

private class FakeWatchlists : com.bofedge.domain.repository.WatchlistRepository {
    override suspend fun list(): ApiResult<List<com.bofedge.domain.model.Watchlist>> =
        ApiResult.Success(emptyList())
    override suspend fun create(name: String) = error("unused")
    override suspend fun rename(id: String, newName: String) = error("unused")
    override suspend fun delete(id: String) = error("unused")
    override suspend fun addItem(watchlistId: String, instrumentId: String, alertEnabled: Boolean) = error("unused")
    override suspend fun removeItem(watchlistId: String, instrumentId: String) = error("unused")
    override suspend fun setAlert(watchlistId: String, instrumentId: String, enabled: Boolean) = error("unused")
}

@OptIn(ExperimentalCoroutinesApi::class)
class ScannerViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @Before fun setUp() { Dispatchers.setMain(dispatcher) }
    @After fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun `initial load fetches first page`() = runTest {
        val repo = FakeRepo().apply { pages = listOf(PageResult(List(25) { inst(it) }, 40, 0)) }
        val vm = ScannerViewModel(repo, FakeWatchlists())
        advanceTimeBy(1_000); runCurrent()
        assertEquals(25, vm.state.value.items.size)
        assertFalse(vm.state.value.endReached)
    }

    @Test
    fun `loadMore appends second page and stops at total`() = runTest {
        val repo = FakeRepo().apply {
            pages = listOf(
                PageResult((0..24).map { inst(it) }, 30, 0),
                PageResult((100..104).map { inst(it) }, 30, 25),
            )
        }
        val vm = ScannerViewModel(repo, FakeWatchlists())
        advanceTimeBy(1_000); runCurrent()
        vm.loadMore()
        advanceTimeBy(1_000); runCurrent()
        assertEquals(30, vm.state.value.items.size)
        assertTrue(vm.state.value.endReached)
        // ids stay distinct across page boundary
        assertEquals(30, vm.state.value.items.map { it.id }.distinct().size)
    }

    @Test
    fun `query changes are debounced into a single reload`() = runTest {
        val repo = FakeRepo().apply {
            pages = listOf(PageResult(emptyList(), 0, 0), PageResult(emptyList(), 0, 0))
        }
        val vm = ScannerViewModel(repo, FakeWatchlists())
        advanceTimeBy(1_000); runCurrent()
        val before = repo.searches.size

        vm.onQueryChange("T")
        advanceTimeBy(100)
        vm.onQueryChange("TC")
        advanceTimeBy(100)
        vm.onQueryChange("TCS")
        // still inside debounce window
        assertTrue(vm.state.value.query == "TCS")
        advanceTimeBy(400); runCurrent()

        // exactly one network reload for the three keystrokes (+ initial load before)
        assertEquals(before + 1, repo.searches.size)
    }
}