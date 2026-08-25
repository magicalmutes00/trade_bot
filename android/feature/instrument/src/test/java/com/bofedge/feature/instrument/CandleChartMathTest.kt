package com.bofedge.feature.instrument

import com.bofedge.domain.model.Candle
import com.bofedge.feature.instrument.chart.CandleChartMath
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private fun candle(o: Double, h: Double, l: Double, c: Double, v: Long = 100) =
    Candle(0L, o, h, l, c, v)

class CandleChartMathTest {

    @Test
    fun `price scale pads beyond extremes`() {
        val s = CandleChartMath.priceScale(listOf(candle(100.0, 110.0, 95.0, 105.0)))!!
        assertTrue(s.paddedMin < 95.0)
        assertTrue(s.paddedMax > 110.0)
        assertEquals(3, s.gridLines.size)
    }

    @Test
    fun `flat series still produces a usable scale`() {
        val s = CandleChartMath.priceScale(listOf(candle(100.0, 100.0, 100.0, 100.0)))!!
        assertTrue(s.paddedMax > s.paddedMin)
        val y = CandleChartMath.yFraction(100.0, s)
        assertTrue(y in 0f..1f)
    }

    @Test
    fun `y fraction maps high to top and low to bottom`() {
        val s = CandleChartMath.priceScale(listOf(candle(100.0, 110.0, 95.0, 105.0)))!!
        assertEquals(0.5f, CandleChartMath.yFraction((s.paddedMax + s.paddedMin) / 2, s))
        assertTrue(CandleChartMath.yFraction(s.paddedMax, s) <= 0.001f)
        assertTrue(CandleChartMath.yFraction(s.paddedMin, s) >= 0.999f)
    }

    @Test
    fun `volume fractions normalise against tallest bar`() {
        val vols = CandleChartMath.volumeFractions(
            listOf(candle(1.0, 2.0, 0.5, 1.5, v = 200), candle(1.0, 2.0, 0.5, 1.5, v = 100)),
        )
        assertEquals(1f, vols[0])
        assertEquals(0.5f, vols[1])
    }

    @Test
    fun `empty input yields null scale`() {
        assertNull(CandleChartMath.priceScale(emptyList()))
        assertNotNull(CandleChartMath.priceScale(listOf(candle(1.0, 2.0, 0.5, 1.5))))
    }
}
