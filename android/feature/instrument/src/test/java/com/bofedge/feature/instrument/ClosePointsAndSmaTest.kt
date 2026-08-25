package com.bofedge.feature.instrument

import com.bofedge.domain.model.Candle
import com.bofedge.feature.instrument.chart.CandleChartMath
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ClosePointsAndSmaTest {

    private fun candle(t: Long, close: Double) = Candle(t, close, close, close, close, 10)

    @Test
    fun `closePoints preserve order and values`() {
        val pts = CandleChartMath.closePoints(
            listOf(candle(100L, 5.0), candle(200L, 6.5), candle(300L, 4.25)),
        )
        assertEquals(listOf(100L to 5.0, 200L to 6.5, 300L to 4.25), pts)
    }

    @Test
    fun `sma warm-up nulls then correct averages`() {
        val candles = (1..10).map { candle(it.toLong(), it.toDouble()) } // closes 1..10
        val sma = CandleChartMath.sma(candles, period = 5)

        assertEquals(10, sma.size)
        assertNull(sma[3])                       // warm-up
        assertEquals(3.0, sma[4]!!, 1e-9)        // mean(1,2,3,4,5)
        assertEquals(8.0, sma[9]!!, 1e-9)        // mean(6..10)
    }

    @Test
    fun `sma with period larger than series is all nulls`() {
        val sma = CandleChartMath.sma((1..5).map { candle(it.toLong(), it.toDouble()) }, period = 20)
        assertTrue(sma.all { it == null })
    }
}
