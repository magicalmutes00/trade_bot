package com.bofedge.feature.instrument

import com.bofedge.domain.model.Candle
import com.bofedge.domain.model.PatternDirection
import com.bofedge.domain.model.StrictPatternEngine
import com.bofedge.domain.model.StrictPatternStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.OffsetDateTime
import kotlin.math.round

/**
 * Port of `backend/tests/engine/test_patterns.py` (1:1) proving the Kotlin
 * StrictPatternEngine matches the backend's Double Top / Double Bottom rules.
 *
 * Bar construction is identical to the backend's `series()`/`mk_series_timed()`
 * and every assertion reproduces the same expected values.
 */
class StrictPatternEngineTest {

    private val t0 = OffsetDateTime.parse("2026-01-05T09:15:00Z").toInstant().toEpochMilli()
    private val step15Ms = 15 * 60 * 1000L

    private fun bar(i: Int, h: Double, l: Double, c: Double? = null): Candle {
        val open = (h + l) / 2
        val close = c ?: open
        return Candle(timeMillis = t0 + step15Ms * i, open = open, high = h, low = l, close = close, volume = 1000)
    }

    private fun series(pairs: List<List<Double>>): List<Candle> = pairs.mapIndexed { i, t ->
        bar(i, t[0], t[1], t.getOrNull(2))
    }

    /** Like [series] but with a configurable bar spacing (for the 9-month rule). */
    private fun seriesTimed(pairs: List<List<Double>>, stepMinutes: Long): List<Candle> =
        pairs.mapIndexed { i, t ->
            Candle(
                timeMillis = t0 + stepMinutes * 60_000L * i,
                open = (t[0] + t[1]) / 2,
                high = t[0],
                low = t[1],
                close = t.getOrNull(2) ?: (t[0] + t[1]) / 2,
                volume = 1000,
            )
        }

    private fun detect(pairs: List<List<Double>>): List<com.bofedge.domain.model.StrictPatternHit> {
        val candles = series(pairs)
        val structure = StrictPatternEngine.analyse(candles, left = 1, right = 1)
        return StrictPatternEngine.detectPatterns(structure, candles)
    }

    // ── Double Top ──────────────────────────────────────────────────────────

    @Test
    fun `double_top_fully_formed`() {
        // peak1=100.0, peak2=100.2 → slippage 0.20% ≤ 0.32%
        val pairs = listOf(
            listOf(98.0, 96.0), listOf(99.0, 97.0), listOf(100.0, 98.0),   // peak1 ~100 (idx 2)
            listOf(99.0, 91.0), listOf(98.0, 92.0), listOf(96.0, 90.0),    // valley ~90 (idx 5)
            listOf(95.0, 93.0), listOf(97.0, 94.6), listOf(100.2, 96.0),   // peak2 ~100.2 (idx 8)
            listOf(99.0, 88.0, 88.0), listOf(96.0, 85.0, 85.0),            // close below neckline 90
        )
        val candles = series(pairs)
        val s = StrictPatternEngine.analyse(candles, left = 1, right = 1)
        val hits = StrictPatternEngine.detectDoubleTop(s, candles)

        assertEquals(1, hits.size)
        val h = hits[0]
        assertEquals("DOUBLE_TOP", h.name)
        assertEquals(PatternDirection.BEARISH, h.direction)
        assertEquals(StrictPatternStatus.FULLY_FORMED, h.status)
        assertEquals(90.0, h.necklinePrice, 1e-9)
        assertEquals(90.0, h.entry, 1e-9)
        assertEquals(9, h.confirmIndex)                     // first close at 88 < 90
        assertEquals(round4(90.0 - 10.1), h.targets[0], 1e-9)
        assertEquals(100.2, h.stopLoss!!, 1e-9)             // higher of the two tops
        assertTrue(h.invalidation.contains("CLOSES above"))
    }

    @Test
    fun `double_top_forming_no_break`() {
        val pairs = listOf(
            listOf(98.0, 96.0), listOf(99.0, 97.0), listOf(100.0, 98.0),
            listOf(99.0, 91.0), listOf(98.0, 92.0), listOf(96.0, 90.0),
            listOf(95.0, 93.0), listOf(97.0, 94.6), listOf(100.2, 96.0),
            listOf(97.0, 92.0), listOf(96.0, 93.0), listOf(97.0, 94.0),
        )
        val hits = StrictPatternEngine.detectDoubleTop(
            StrictPatternEngine.analyse(series(pairs), left = 1, right = 1), series(pairs),
        )

        assertEquals(1, hits.size)
        assertEquals(StrictPatternStatus.FORMING, hits[0].status)
        assertEquals(null, hits[0].confirmIndex)
        assertTrue(hits[0].confidence <= 0.5)              // FORMING caps confidence
    }

    @Test
    fun `double_top_peak_tolerance_rejects`() {
        val pairs = listOf(
            listOf(90.0, 88.0), listOf(95.0, 92.0), listOf(100.0, 98.0),  // peak1 ~100
            listOf(99.0, 91.0), listOf(98.0, 92.0), listOf(96.0, 90.0),   // valley ~90
            listOf(95.0, 93.0), listOf(97.0, 94.0), listOf(105.0, 102.0), // peak2 ~105 → 4.9%
            listOf(103.0, 88.0, 88.0),
        )
        val hits = detect(pairs)
        assertTrue(hits.isEmpty())
    }

    @Test
    fun `double_top_nine_month_window`() {
        val pairs = listOf(
            listOf(98.0, 96.0), listOf(99.0, 97.0), listOf(100.0, 98.0),   // peak1 ~100
            listOf(99.0, 91.0), listOf(98.0, 92.0), listOf(96.0, 89.0),    // valley ~89
            listOf(95.0, 93.0), listOf(97.0, 95.0), listOf(100.2, 96.0),   // peak2 300 days later
            listOf(99.0, 88.0, 88.0),
        )
        // 50 days per bar → 6 intervals = 300 days > 274
        val stepMinutes = 50L * 24 * 60
        val candles = seriesTimed(pairs, stepMinutes)
        val s = StrictPatternEngine.analyse(candles, left = 1, right = 1)
        val hits = StrictPatternEngine.detectDoubleTop(s, candles)
        assertTrue(hits.isEmpty())
    }

    @Test
    fun `double_top_wick_cross_does_not_confirm`() {
        val pairs = listOf(
            listOf(98.0, 96.0), listOf(99.0, 97.0), listOf(100.0, 98.0),
            listOf(99.0, 91.0), listOf(98.0, 92.0), listOf(96.0, 90.0),
            listOf(95.0, 93.0), listOf(97.0, 94.6), listOf(100.2, 96.0),
            listOf(98.0, 89.0, 96.0),                       // low 89 < 90 (wick) but close 96 > 90
            listOf(97.0, 94.0, 95.0),
        )
        val hits = detect(pairs)
        assertEquals(1, hits.size)
        assertEquals(StrictPatternStatus.FORMING, hits[0].status)   // wick alone does not confirm
    }

    // ── Double Bottom ───────────────────────────────────────────────────────

    @Test
    fun `double_bottom_fully_formed`() {
        // valley1=80.0, valley2=80.2 → slippage 0.25% ≤ 0.32%
        val pairs = listOf(
            listOf(88.0, 84.0), listOf(86.0, 82.0), listOf(84.0, 80.0),  // bottom1 ~80 (idx 2)
            listOf(86.0, 83.0), listOf(90.0, 88.0), listOf(95.0, 93.0),  // peak ~95 (idx 5)
            listOf(94.0, 88.0), listOf(89.0, 82.0), listOf(86.0, 80.2),  // bottom2 ~80.2 (idx 8)
            listOf(97.0, 95.0, 96.0),                                    // close above neckline 95
        )
        val candles = series(pairs)
        val s = StrictPatternEngine.analyse(candles, left = 1, right = 1)
        val hits = StrictPatternEngine.detectDoubleBottom(s, candles)

        assertEquals(1, hits.size)
        val h = hits[0]
        assertEquals("DOUBLE_BOTTOM", h.name)
        assertEquals(PatternDirection.BULLISH, h.direction)
        assertEquals(StrictPatternStatus.FULLY_FORMED, h.status)
        assertEquals(95.0, h.necklinePrice, 1e-9)
        assertEquals(95.0, h.entry, 1e-9)
        assertEquals(9, h.confirmIndex)
        assertEquals(round4(95.0 + 14.9), h.targets[0], 1e-9)
        assertEquals(80.0, h.stopLoss!!, 1e-9)              // lower of the two bottoms
        assertTrue(h.invalidation.contains("CLOSES below"))
    }

    @Test
    fun `double_bottom_forming_no_break`() {
        val pairs = listOf(
            listOf(88.0, 84.0), listOf(86.0, 82.0), listOf(84.0, 80.0),
            listOf(86.0, 83.0), listOf(90.0, 88.0), listOf(95.0, 93.0),
            listOf(94.0, 88.0), listOf(89.0, 82.0), listOf(86.0, 80.2),
            listOf(90.0, 88.0), listOf(92.0, 90.0), listOf(93.0, 91.0),  // no close above 95
        )
        val hits = detect(pairs)
        assertEquals(1, hits.size)
        assertEquals(StrictPatternStatus.FORMING, hits[0].status)
    }

    // ── Combined ────────────────────────────────────────────────────────────

    @Test
    fun `detect_patterns_returns_both_sorted_by_confirm`() {
        val pairs = listOf(
            // Double bottom FIRST (confirms at idx 9)
            listOf(88.0, 84.0), listOf(86.0, 82.0), listOf(84.0, 80.0),
            listOf(86.0, 83.0), listOf(90.0, 88.0), listOf(95.0, 93.0),
            listOf(94.0, 88.0), listOf(89.0, 82.0), listOf(86.0, 80.2),
            listOf(97.0, 95.0, 96.0),
            // Double top LATER (confirms at idx ~20)
            listOf(96.0, 94.0), listOf(97.0, 95.0), listOf(100.0, 98.0),
            listOf(99.0, 91.0), listOf(98.0, 92.0), listOf(96.0, 90.0),
            listOf(95.0, 93.0), listOf(97.0, 94.6), listOf(100.2, 96.0),
            listOf(99.0, 88.0, 88.0), listOf(96.0, 85.0, 85.0),
        )
        val hits = detect(pairs)

        assertEquals(2, hits.size)
        assertEquals("DOUBLE_TOP", hits[0].name)
        assertEquals(StrictPatternStatus.FULLY_FORMED, hits[0].status)
        assertEquals("DOUBLE_BOTTOM", hits[1].name)
        assertEquals(StrictPatternStatus.FULLY_FORMED, hits[1].status)
    }

    // ── Edge cases ──────────────────────────────────────────────────────────

    @Test
    fun `no_patterns_when_insufficient_swings`() {
        val pairs = MutableList(50) { listOf(100.0, 99.0) }
        val candles = series(pairs)
        val s = StrictPatternEngine.analyse(candles, left = 2, right = 2)
        assertTrue(StrictPatternEngine.detectPatterns(s, candles).isEmpty())
    }

    @Test
    fun `confidence_in_unit_range`() {
        val pairs = listOf(
            listOf(98.0, 96.0), listOf(99.0, 97.0), listOf(100.0, 98.0),
            listOf(99.0, 91.0), listOf(98.0, 92.0), listOf(96.0, 90.0),
            listOf(95.0, 93.0), listOf(97.0, 94.6), listOf(100.2, 96.0),
            listOf(99.0, 88.0, 88.0), listOf(96.0, 85.0, 85.0),
        )
        val hits = detect(pairs)
        assertTrue(hits.isNotEmpty())
        for (h in hits) {
            assertTrue(h.confidence in 0.0..1.0)
        }
    }

    private fun round4(x: Double): Double = round(x * 10000.0) / 10000.0
}
