package com.bofedge.feature.instrument.chart

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.bofedge.domain.model.Candle

enum class ChartMode { CANDLES, LINE, AREA }

private val BULL = Color(0xFF16C784)
private val BEAR = Color(0xFFEA3943)
private val GRID = Color(0xFF232D3D)
private val AXIS_TEXT = Color(0xFF8A97A8)
private val LINE_COLOR = Color(0xFF4E9CFF)

/**
 * Dispatcher for the chart area. All modes share the price grid, right-side
 * axis and the volume pane; the SMA(20) overlay draws on top when enabled.
 */
@Composable
fun PriceChart(
    mode: ChartMode,
    showSma: Boolean,
    candles: List<Candle>,
    modifier: Modifier = Modifier,
) {
    if (candles.isEmpty()) return

    val scale = CandleChartMath.priceScale(candles) ?: return
    val vols = CandleChartMath.volumeFractions(candles)
    val smaValues = if (showSma) CandleChartMath.sma(candles) else null

    Row(modifier.fillMaxWidth()) {
        Box(Modifier.weight(1f).height(240.dp)) {
            Canvas(Modifier.fillMaxSize()) {
                val w = size.width
                val priceH = size.height * 0.78f
                val volTop = size.height * 0.84f
                val volMaxH = size.height * 0.15f

                scale.gridLines.forEach { level ->
                    val y = priceH * CandleChartMath.yFraction(level, scale)
                    drawLine(GRID, Offset(0f, y), Offset(w, y), strokeWidth = 1f)
                }

                fun yPrice(p: Double): Float = priceH * CandleChartMath.yFraction(p, scale)
                val step = w / candles.size
                val bodyW = (step * 0.62f).coerceAtLeast(1.5f)

                // ---- volume pane (all modes) ----
                candles.forEachIndexed { i, c ->
                    vols.getOrNull(i)?.let { frac ->
                        val h = volMaxH * frac
                        val color =
                            if (c.isBullish) BULL.copy(alpha = 0.45f) else BEAR.copy(alpha = 0.45f)
                        drawRect(
                            color,
                            topLeft = Offset(step * i + step / 2f - bodyW / 2f,
                                             volTop + (volMaxH - h)),
                            size = Size(bodyW, h),
                        )
                    }
                }

                // ---- price series per mode ----
                when (mode) {
                    ChartMode.CANDLES -> drawCandles(
                        candles, ::yPrice, step, bodyW,
                    )
                    ChartMode.LINE -> drawClosePath(
                        candles, ::yPrice, step,
                        fillArea = false, priceH = priceH,
                    )
                    ChartMode.AREA -> drawClosePath(
                        candles, ::yPrice, step,
                        fillArea = true, priceH = priceH,
                    )
                }

                // ---- SMA(20) overlay ----
                smaValues?.let { values ->
                    val path = Path()
                    var started = false
                    candles.forEachIndexed { i, c ->
                        val v = values.getOrNull(i) ?: return@forEachIndexed
                        val x = step * i + step / 2f
                        val y = yPrice(v)
                        if (!started) {
                            path.moveTo(x, y); started = true
                        } else {
                            path.lineTo(x, y)
                        }
                    }
                    drawPath(
                        path,
                        color = LINE_COLOR.copy(alpha = 0.9f),
                        style = Stroke(
                            width = 2f,
                            cap = StrokeCap.Round,
                            pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f)),
                        ),
                    )
                }
            }

            Column(
                Modifier
                    .align(Alignment.TopEnd)
                    .fillMaxHeight()
                    .width(56.dp),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                AxisLabel("%.2f".format(scale.paddedMax), Modifier.align(Alignment.End))
                AxisLabel("%.2f".format((scale.paddedMax + scale.paddedMin) / 2),
                          Modifier.align(Alignment.End))
                AxisLabel("%.2f".format(scale.paddedMin), Modifier.align(Alignment.End))
            }
        }
    }
}

// ------------------------------------------------------------------ layers

private fun DrawScope.drawCandles(
    candles: List<Candle>,
    yPrice: (Double) -> Float,
    step: Float,
    bodyW: Float,
) {
    candles.forEachIndexed { i, c ->
        val cx = step * i + step / 2f
        val color = if (c.isBullish) BULL else BEAR

        drawLine(color, Offset(cx, yPrice(c.high)), Offset(cx, yPrice(c.low)), strokeWidth = 2f)

        val top = yPrice(maxOf(c.open, c.close))
        val bottom = yPrice(minOf(c.open, c.close))
        drawRoundRect(
            color,
            topLeft = Offset(cx - bodyW / 2f, top),
            size = Size(bodyW, (bottom - top).coerceAtLeast(2f)),
            cornerRadius = CornerRadius(2f, 2f),
        )
    }
}

private fun DrawScope.drawClosePath(
    candles: List<Candle>,
    yPrice: (Double) -> Float,
    step: Float,
    fillArea: Boolean,
    priceH: Float,
) {
    if (candles.isEmpty()) return

    val line = Path()
    candles.forEachIndexed { i, c ->
        val x = step * i + step / 2f
        val y = yPrice(c.close)
        if (i == 0) line.moveTo(x, y) else line.lineTo(x, y)
    }

    if (fillArea) {
        val area = Path().apply {
            addPath(line)
            lineTo(step * (candles.size - 1) + step / 2f, priceH)
            lineTo(step * 0 + step / 2f, priceH)
            close()
        }
        drawPath(
            area,
            brush = Brush.verticalGradient(
                colors = listOf(LINE_COLOR.copy(alpha = 0.35f), Color.Transparent),
                startY = 0f,
                endY = priceH,
            ),
        )
    }

    drawPath(line, color = LINE_COLOR, style = Stroke(width = 3f, cap = StrokeCap.Round))

    // last-close dot
    val last = candles.last()
    drawCircle(
        LINE_COLOR,
        radius = 5f,
        center = Offset(step * (candles.size - 1) + step / 2f, yPrice(last.close)),
    )
}

// ------------------------------------------------------------------ labels

@Composable
private fun AxisLabel(value: String, modifier: Modifier = Modifier) {
    Text(value, style = MaterialTheme.typography.labelSmall, color = AXIS_TEXT, modifier = modifier)
}
