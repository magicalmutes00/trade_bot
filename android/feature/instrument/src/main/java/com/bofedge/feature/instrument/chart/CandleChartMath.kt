package com.bofedge.feature.instrument.chart

import com.bofedge.domain.model.Candle
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.pow
import kotlin.math.round
import kotlin.math.sqrt

data class PriceScale(
    val min: Double,
    val max: Double,
    val paddedMin: Double,
    val paddedMax: Double,
    val gridLines: List<Double>,
)

/**
 * TradingView-style price scale: bounds snapped to a "nice" step (1/2/2.5/5 ×
 * 10^n) so gridlines land on round numbers and stay put while data jitters.
 */
data class NicePriceScale(
    val paddedMin: Double,
    val paddedMax: Double,
    val ticks: List<Double>,
    val step: Double,
    /** Decimals needed to render [step] exactly — used for all price labels. */
    val decimals: Int,
)

object CandleChartMath {

    fun priceScale(candles: List<Candle>): PriceScale? {
        if (candles.isEmpty()) return null
        val min = candles.minOf { it.low }
        val max = candles.maxOf { it.high }
        val span = (max - min).takeIf { it > 0 } ?: (max * 0.01).takeIf { it > 0 } ?: 1.0
        val pad = span * 0.06
        val pMin = min - pad
        val pMax = max + pad
        return PriceScale(
            min = min, max = max, paddedMin = pMin, paddedMax = pMax,
            gridLines = listOf(pMin, pMin + (pMax - pMin) / 2, pMax),
        )
    }

    /**
     * Nice-number scale (lightweight-charts behaviour):
     * 1. pad raw range symmetrically;
     * 2. pick step from {1, 2, 2.5, 5} × 10^n closest under range/targetTicks;
     * 3. snap bounds outwards to step multiples → ticks are round numbers.
     */
    fun nicePriceScale(candles: List<Candle>, targetTicks: Int = 6): NicePriceScale? {
        if (candles.isEmpty()) return null
        val rawMin = candles.minOf { it.low }
        val rawMax = candles.maxOf { it.high }
        val span = (rawMax - rawMin).takeIf { it > 0 } ?: (rawMax * 0.01).takeIf { it > 0 } ?: 1.0
        val pad = span * 0.08
        val lo = rawMin - pad
        val hi = rawMax + pad

        var step = niceCeil((hi - lo) / max(targetTicks, 1))
        // Guard against pathological zero/negative steps.
        if (step <= 0.0 || step.isNaN()) step = 1.0

        val first = ceil(lo / step - 1e-9) * step
        val ticks = mutableListOf<Double>()
        var t = first
        var guard = 0
        while (t <= hi + step * 1e-9 && guard < 512) {
            ticks += t
            t += step
            guard++
        }

        return NicePriceScale(
            paddedMin = first.coerceAtMost(lo),
            paddedMax = (ticks.lastOrNull() ?: hi).coerceAtLeast(hi),
            ticks = ticks,
            step = step,
            decimals = decimalsFor(step),
        )
    }

    private fun niceCeil(raw: Double): Double {
        if (raw <= 0.0 || raw.isNaN() || raw.isInfinite()) return 1.0
        val mag = 10.0.pow(floor(log10(raw)))
        val norm = raw / mag
        val nice = when {
            norm <= 1.0 -> 1.0
            norm <= 2.0 -> 2.0
            norm <= 2.5 -> 2.5
            norm <= 5.0 -> 5.0
            else -> 10.0
        }
        return nice * mag
    }

    internal fun decimalsFor(step: Double): Int {
        var s = step
        var d = 0
        while (d < 6 && abs(s - round(s)) > 1e-6) {
            s *= 10
            d++
        }
        return d
    }

    fun formatPrice(value: Double, decimals: Int): String =
        "%.${decimals.coerceIn(0, 6)}f".format(value)

    /**
     * Absolute indices of bars to label on the time axis, chosen so adjacent
     * labels never overlap (step ≥ minLabelGapPx / pxPerBar, snapped to a
     * friendly 1/2/3/5/10/15/30/60 rhythm) and aligned to absolute index
     * multiples so labels don't flicker while panning.
     */
    fun timeTickIndices(
        startIdx: Int,
        endIdxExclusive: Int,
        pxPerBar: Float,
        minLabelGapPx: Float,
    ): List<Int> {
        if (endIdxExclusive <= startIdx) return emptyList()
        val minStep = ceil(minLabelGapPx / max(pxPerBar, 0.5f)).toInt().coerceAtLeast(1)
        var step = RHYTHM.firstOrNull { it >= minStep } ?: run {
            var s = RHYTHM.last()
            while (s < minStep) s *= 2
            s
        }
        val first = ceil(startIdx.toDouble() / step).toInt() * step
        return generateSequence(first) { it + step }
            .takeWhile { it < endIdxExclusive }
            .toList()
    }

    private val RHYTHM = intArrayOf(1, 2, 3, 5, 10, 15, 30, 60)

    fun yFraction(price: Double, scale: PriceScale): Float {
        val span = scale.paddedMax - scale.paddedMin
        if (span <= 0) return 0.5f
        return ((scale.paddedMax - price) / span).toFloat().coerceIn(0f, 1f)
    }

    fun volumeFractions(candles: List<Candle>): List<Float> {
        val maxV = candles.maxOfOrNull { it.volume } ?: return candles.map { 0f }
        if (maxV <= 0) return candles.map { 0f }
        return candles.map { (it.volume.toFloat() / maxV).coerceIn(0.04f, 1f) }
    }

    fun closePoints(candles: List<Candle>): List<Pair<Long, Double>> =
        candles.map { it.timeMillis to it.close }

    fun sma(candles: List<Candle>, period: Int): List<Double?> {
        if (period <= 0) return candles.map { null }
        val out = mutableListOf<Double?>()
        var sum = 0.0
        for (i in candles.indices) {
            sum += candles[i].close
            if (i >= period) sum -= candles[i - period].close
            out += if (i >= period - 1) sum / period else null
        }
        return out
    }

    fun ema(candles: List<Candle>, period: Int): List<Double?> {
        if (period <= 0 || candles.isEmpty()) return candles.map { null }
        val k = 2.0 / (period + 1)
        val closes = candles.map { it.close }
        val out = mutableListOf<Double?>()
        var prev = closes[0]
        for (i in closes.indices) {
            if (i < period - 1) { out += null; continue }
            if (i == period - 1) {
                prev = closes.subList(0, period).average()
                out += prev; continue
            }
            prev = closes[i] * k + prev * (1 - k)
            out += prev
        }
        return out
    }

    data class BollingerBands(
        val upper: List<Double?>, val mid: List<Double?>, val lower: List<Double?>,
    )

    fun bollinger(candles: List<Candle>, period: Int = 20, mult: Double = 2.0): BollingerBands {
        val closes = candles.map { it.close }
        val n = closes.size
        val upper = mutableListOf<Double?>()
        val mid = mutableListOf<Double?>()
        val lower = mutableListOf<Double?>()
        for (i in 0 until n) {
            if (i < period - 1) { upper += null; mid += null; lower += null; continue }
            val window = closes.subList(i - period + 1, i + 1)
            val mean = window.average()
            val std = sqrt(window.sumOf { (it - mean) * (it - mean) } / period)
            mid += mean; upper += mean + mult * std; lower += mean - mult * std
        }
        return BollingerBands(upper, mid, lower)
    }

    fun rsi(candles: List<Candle>, period: Int = 14): List<Double?> {
        if (candles.size <= period) return candles.map { null }
        val out = mutableListOf<Double?>()
        out += null
        var avgGain = 0.0; var avgLoss = 0.0
        for (i in 1..period) {
            val chg = candles[i].close - candles[i - 1].close
            if (chg > 0) avgGain += chg else avgLoss -= chg
        }
        avgGain /= period; avgLoss /= period
        out += _rsiValue(avgGain, avgLoss)
        for (i in period + 1 until candles.size) {
            val chg = candles[i].close - candles[i - 1].close
            avgGain = (avgGain * (period - 1) + maxOf(chg, 0.0)) / period
            avgLoss = (avgLoss * (period - 1) + maxOf(-chg, 0.0)) / period
            out += _rsiValue(avgGain, avgLoss)
        }
        return out
    }

    private fun _rsiValue(gain: Double, loss: Double): Double? {
        if (loss == 0.0 && gain == 0.0) return 50.0
        if (loss == 0.0) return 100.0
        return 100.0 - (100.0 / (1.0 + gain / loss))
    }

    fun lastPriceDeltaPercent(candles: List<Candle>): Double? {
        if (candles.size < 2) return null
        val first = candles.first().open
        val last = candles.last().close
        if (abs(first) < 1e-9) return null
        return (last - first) / first * 100.0
    }
}
