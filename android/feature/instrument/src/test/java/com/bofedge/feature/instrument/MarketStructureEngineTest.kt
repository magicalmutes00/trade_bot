package com.bofedge.feature.instrument

import com.bofedge.domain.model.Candle
import com.bofedge.domain.model.MarketStructure
import com.bofedge.domain.model.MarketStructureEngine
import com.bofedge.domain.model.PatternDirection
import com.bofedge.domain.model.SwingPoint
import com.bofedge.domain.model.SwingPointDirection
import com.bofedge.domain.model.Trend
import com.bofedge.domain.model.Timeframe
import com.bofedge.domain.model.SwingDetectionConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

private fun candle(o: Double, h: Double, l: Double, c: Double, v: Long = 100, tf: Timeframe = Timeframe.DAILY) =
    Candle(0L, o, h, l, c, v, tf)

class MarketStructureEngineTest {

    @Test
    fun `bullish trend detection with HH HL pattern`() {
        // Create candles with rising prices (higher highs and higher lows)
        val candles = listOf(
            candle(100.0, 105.0, 95.0, 102.0), // bar 0: high 105, low 95, close 102
            candle(102.0, 110.0, 100.0, 108.0), // bar 1: higher high, higher close
            candle(108.0, 115.0, 105.0, 112.0), // bar 2: higher high, higher close
            candle(112.0, 120.0, 110.0, 118.0)  // bar 3: higher high, higher close
        )

        val structure = MarketStructureEngine.analyze(candles, SwingDetectionConfig(swingLookback = 1))

        assertNotNull(structure)
        assertEquals(Trend.BULLISH, structure.trend)
        assertTrue(structure.confidence > 0.0)
        assertTrue(structure.swingPoints.isNotEmpty())
    }

    @Test
    fun `bearish trend detection with LL LH pattern`() {
        // Create candles with falling prices (lower lows and lower highs)
        val candles = listOf(
            candle(120.0, 115.0, 110.0, 112.0), // bar 0: high 115, low 110, close 112
            candle(112.0, 108.0, 100.0, 105.0), // bar 1: lower low, lower close
            candle(105.0, 100.0, 95.0, 98.0),   // bar 2: lower low, lower close
            candle(98.0, 92.0, 88.0, 90.0)      // bar 3: lower low, lower close
        )

        val structure = MarketStructureEngine.analyze(candles, SwingDetectionConfig(swingLookback = 1))

        assertNotNull(structure)
        assertEquals(Trend.BEARISH, structure.trend)
        assertTrue(structure.confidence > 0.0)
    }

    @Test
    fun `neutral trend with insufficient data`() {
        val candles = listOf(
            candle(100.0, 105.0, 95.0, 102.0),
            candle(102.0, 103.0, 101.0, 102.5)
        )

        val structure = MarketStructureEngine.analyze(candles)

        assertNotNull(structure)
        assertEquals(Trend.NEUTRAL, structure.trend)
        assertTrue(structure.confidence < 0.5) // low confidence with little data
    }

    @Test
    fun `swing_points_detected`() {
        val candles = listOf(
            candle(100.0, 110.0, 90.0, 95.0), // potential swing high at bar 0
            candle(95.0, 98.0, 92.0, 95.0),
            candle(95.0, 105.0, 92.0, 100.0), // potential swing high
            candle(100.0, 108.0, 98.0, 105.0),
            candle(105.0, 115.0, 102.0, 110.0) // potential swing high
        )

        val structure = MarketStructureEngine.analyze(candles)

        assertNotNull(structure)
        assertTrue(structure.swingPoints.size >= 2)
        // Check that we have both high and low swing points
        val directions = structure.swingPoints.map { it.direction }
        assertTrue(directions.contains(SwingPointDirection.HIGH))
        assertTrue(directions.contains(SwingPointDirection.LOW))
    }

    @Test
    fun `support_resistance_levels`() {
        val candles = listOf(
            candle(100.0, 110.0, 90.0, 95.0),
            candle(95.0, 98.0, 92.0, 95.0),
            candle(95.0, 105.0, 92.0, 100.0),
            candle(100.0, 108.0, 98.0, 105.0),
            candle(105.0, 115.0, 102.0, 110.0)
        )

        val structure = MarketStructureEngine.analyze(candles)

        assertNotNull(structure.supportResistance)
        // Should have at least some pivot levels computed
        assertTrue(structure.supportResistance.pivotLows.isNotEmpty() ||
            structure.supportResistance.pivotHighs.isNotEmpty())
    }

    @Test
    fun `market_structure_with_lookback_config`() {
        val candles = listOf(
            candle(100.0, 110.0, 95.0, 105.0),
            candle(105.0, 115.0, 100.0, 112.0),
            candle(112.0, 120.0, 110.0, 118.0),
            candle(118.0, 125.0, 115.0, 122.0),
            candle(122.0, 130.0, 120.0, 128.0)
        )

        val config = SwingDetectionConfig(swingLookback = 2)
        val structure = MarketStructureEngine.analyze(candles, config)

        assertNotNull(structure)
        assertTrue(structure.confidence > 0.0)
    }
}