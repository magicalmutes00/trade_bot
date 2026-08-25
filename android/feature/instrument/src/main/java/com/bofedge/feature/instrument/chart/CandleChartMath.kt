package com.bofedge.feature.instrument.chart

import com.bofedge.domain.model.Candle
import kotlin.math.abs

/**
 * Pure chart-scaling math (unit-tested) so the Compose Canvas stays dumb.
 */
data class PriceScale(
    val min: Double,
    val max: Double,
    val paddedMin: Double,
    val paddedMax: Double,
    val gridLines: List<Double>,   // 3 evenly spaced levels (min/mid/max padded)
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

    /** Map a price to a vertical fraction in [0,1] (0 = top of chart). */
    fun yFraction(price: Double, scale: PriceScale): Float {
        val span = scale.paddedMax - scale.paddedMin
        if (span <= 0) return 0.5f
        return ((scale.paddedMax - price) / span).toFloat().coerceIn(0f, 1f)
    }

    /** Volume bar height fraction in [0,1] relative to the tallest bar. */
    fun volumeFractions(candles: List<Candle>): List<Float> {
        val maxV = candles.maxOfOrNull { it.volume } ?: return candles.map { 0f }
        if (maxV <= 0) return candles.map { 0f }
        return candles.map { (it.volume.toFloat() / maxV).coerceIn(0.04f, 1f) }
    }

    /** Human label for the timeframe chip values used by the app. */
    fun axisLabel(timeMillis: Long): String {
        val cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"))
        cal.timeInMillis = timeMillis
        val month = cal.get(java.util.Calendar.MONTH) + 1
        val day = cal.get(java.util.Calendar.DAY_OF_MONTH)
        val hour = cal.get(java.util.Calendar.HOUR_OF_DAY)
        return if (hour == 0 && cal.get(java.util.Calendar.MINUTE) == 0)
            "%02d/%02d".format(month, day)
        else "%02d:%02d".format(hour, cal.get(java.util.Calendar.MINUTE))
    }

    fun lastPriceDeltaPercent(candles: List<Candle>): Double? {
        if (candles.size < 2) return null
        val first = candles.first().open
        val last = candles.last().close
        if (abs(first) < 1e-9) return null
        return (last - first) / first * 100.0
    }

    // ------------------------------------------------------ indicators

    /** Simple moving average of closes, aligned per index (null during warm-up). */
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

    /** Exponential moving average of closes. First value = first close (seed). */
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
                out += prev
                continue
            }
            prev = closes[i] * k + prev * (1 - k)
            out += prev
        }
        return out
    }

    /**
     * Bollinger Bands — returns aligned lists of upper/mid/lower values.
     * Mid = SMA(period), Upper/Lower = mid ± stddev × mult.
     */
    data class BollingerBands(val upper: List<Double?>, val mid: List<Double?>, val lower: List<Double?>)

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
            val std = kotlin.math.sqrt(window.sumOf { (it - mean) * (it - mean) } / period)
            mid += mean; upper += mean + mult * std; lower += mean - mult * std
        }
        return BollingerBands(upper, mid, lower)
    }

    /** RSI(14) — momentum oscillator [0, 100]. */
    fun rsi(candles: List<Candle>, period: Int = 14): List<Double?> {
        if (candles.size <= period) return candles.map { null }
        val out = mutableListOf<Double?>()
        out += null // index 0 has no prior close to compute change from

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
        val rs = gain / loss
        return 100.0 - (100.0 / (1.0 + rs))
    }

    /** (timeMillis, close) pairs for line & area charts. */
    fun closePoints(candles: List<Candle>): List<Pair<Long, Double>> =
        candles.map { it.timeMillis to it.close }
}
