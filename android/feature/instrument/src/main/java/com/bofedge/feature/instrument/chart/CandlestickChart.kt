package com.bofedge.feature.instrument.chart

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.bofedge.domain.model.Candle

private val BULL = Color(0xFF16C784)
private val BEAR = Color(0xFFEA3943)
private val GRID = Color(0xFF232D3D)
private val AXIS_TEXT = Color(0xFF8A97A8)

/**
 * Candlestick + volume renderer (no chart libraries â€” pure Canvas).
 * Price zone occupies the top 78%, volume bars the bottom 18%.
 */
@Composable
fun CandlestickChart(
    candles: List<Candle>,
    modifier: Modifier = Modifier,
    bullColor: Color = BULL,
    bearColor: Color = BEAR,
) {
    if (candles.isEmpty()) return

    val scale = CandleChartMath.priceScale(candles) ?: return
    val vols = CandleChartMath.volumeFractions(candles)
    val bullishList = candles.map { it.isBullish }

    Row(modifier.fillMaxWidth()) {
        // --- price + volume canvas ---
        Box(modifier.weight(1f).height(240.dp)) {
            Canvas(Modifier.fillMaxSize()) {
                val w = size.width
                val priceH = size.height * 0.78f
                val volTop = size.height * 0.84f
                val volMaxH = size.height * 0.15f

                // grid lines
                scale.gridLines.forEach { level ->
                    val y = priceH * CandleChartMath.yFraction(level, scale)
                    drawLine(GRID, Offset(0f, y), Offset(w, y), strokeWidth = 1f)
                }

                val step = w / candles.size
                val bodyW = (step * 0.62f).coerceAtLeast(1.5f)

                fun yPrice(p: Double): Float =
                    priceH * CandleChartMath.yFraction(p, scale)

                candles.forEachIndexed { i, c ->
                    val cx = step * i + step / 2f
                    val color = if (bullishList[i]) bullColor else bearColor

                    // wick
                    drawLine(
                        color,
                        Offset(cx, yPrice(c.high)),
                        Offset(cx, yPrice(c.low)),
                        strokeWidth = 2f,
                    )

                    // body
                    val top = yPrice(maxOf(c.open, c.close))
                    val bottom = yPrice(minOf(c.open, c.close))
                    drawRoundRect(
                        color,
                        topLeft = Offset(cx - bodyW / 2f, top),
                        size = Size(bodyW, (bottom - top).coerceAtLeast(2f)),
                        cornerRadius = CornerRadius(2f, 2f),
                    )

                    // volume bar
                    vols.getOrNull(i)?.let { frac ->
                        val h = volMaxH * frac
                        drawRect(
                            color.copy(alpha = 0.45f),
                            topLeft = Offset(cx - bodyW / 2f, volTop + (volMaxH - h)),
                            size = Size(bodyW, h),
                        )
                    }
                }
            }

            // right-side price axis labels
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

@Composable
private fun AxisLabel(value: String, modifier: Modifier = Modifier) {
    Text(value, style = MaterialTheme.typography.labelSmall, color = AXIS_TEXT, modifier = modifier)
}


