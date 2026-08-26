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

    // ---------------- nice price scale (lightweight-charts style)

    @Test
    fun `nice scale produces round ticks covering the range`() {
        val s = CandleChartMath.nicePriceScale(listOf(candle(100.0, 110.0, 95.0, 105.0)))!!
        assertTrue(s.ticks.size >= 2)
        assertTrue(s.paddedMin <= 95.0)
        assertTrue(s.paddedMax >= 110.0)
        s.ticks.forEach { t ->
            assertTrue(t >= s.paddedMin && t <= s.paddedMax)
            // "round" means a small multiple of the step
            val ratio = t / s.step
            assertEquals(ratio, kotlin.math.round(ratio), 1e-6)
        }
    }

    @Test
    fun `nice scale decimals represent the step exactly`() {
        val fine = CandleChartMath.nicePriceScale(
            listOf(candle(100.0, 100.6, 100.0, 100.3)),
        )!!
        assertTrue(fine.decimals > 0)
        val coarse = CandleChartMath.nicePriceScale(
            listOf(candle(90.0, 120.0, 88.0, 118.0)),
        )!!
        assertEquals(0, coarse.decimals)
        assertEquals("100.3", CandleChartMath.formatPrice(100.3, fine.decimals))
        assertEquals("105", CandleChartMath.formatPrice(105.0, coarse.decimals))
    }

    @Test
    fun `flat series yields usable nice scale`() {
        val s = CandleChartMath.nicePriceScale(listOf(candle(100.0, 100.0, 100.0, 100.0)))!!
        assertTrue(s.paddedMax > s.paddedMin)
        assertTrue(s.ticks.isNotEmpty())
    }

    @Test
    fun `empty input yields null nice scale`() {
        assertNull(CandleChartMath.nicePriceScale(emptyList()))
    }

    // ---------------- time axis ticks

    @Test
    fun `time ticks respect minimum pixel gap`() {
        val ticks = CandleChartMath.timeTickIndices(
            startIdx = 0, endIdxExclusive = 500,
            pxPerBar = 1f, minLabelGapPx = 36f,
        )
        assertTrue(ticks.isNotEmpty())
        // 1 px/bar and ≥36 px labels → step must be ≥ 36 bars apart
        ticks.zipWithNext().forEach { (a, b) -> assertTrue(b - a >= 36) }
        assertEquals(listOf(0, 60, 120, 180, 240, 300, 360, 420, 480), ticks)
    }

    @Test
    fun `time ticks align to absolute multiples so panning is stable`() {
        val a = CandleChartMath.timeTickIndices(0, 200, pxPerBar = 10f, minLabelGapPx = 36f)
        val b = CandleChartMath.timeTickIndices(37, 237, pxPerBar = 10f, minLabelGapPx = 36f)
        assertEquals(listOf(0, 5), a.take(2))          // bar 0 labelled, then rhythm
        assertEquals(40, b.first())                     // first multiple of 5 ≥ 37
        assertTrue(b.all { it % 5 == 0 })               // same grid while panned
    }
}
