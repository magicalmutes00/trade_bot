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
}
