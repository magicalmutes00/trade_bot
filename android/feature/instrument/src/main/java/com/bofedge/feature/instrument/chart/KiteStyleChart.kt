package com.bofedge.feature.instrument.chart

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.bofedge.domain.model.Candle
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

private val BULL = Color(0xFF16C784)
private val BEAR = Color(0xFFEA3943)
private val GRID = Color(0xFF1A2230)
private val CROSS = Color(0xFF4E9CFF)
private val AXIS_C = Color(0xFF8A97A8)
private val LINE_C = Color(0xFF4E9CFF)
private val TAG_TEXT = Color(0xFFFFFFFF)
private val TAG_TEXT_DARK = Color(0xFF0B1420)

// Geometry constants (lightweight-charts-inspired layout)
private val TIME_AXIS_H = 22.dp
private val AXIS_MIN_W = 46.dp
private val AXIS_PAD = 6.dp
private const val VOL_FRACTION = 0.16f          // volume strip = bottom 16 % of price pane
private const val DEGRADE_PX_PER_BAR = 3f       // below this px/bar → close-line mode

/**
 * TradingView-inspired candlestick chart rendered on a single canvas:
 *  • nice-number price grid + auto-sized right axis (labels align to gridlines)
 *  • smart time axis — labels never overlap, date shown at day changes
 *  • magnet crosshair snapped to bars, with price + time axis tags
 *  • last close pinned on the axis with a direction-coloured tag
 *  • volume overlaid behind price
 *  • degrades to a close-line when bars drop below [DEGRADE_PX_PER_BAR] px
 */
/** Dashed ellipse only when a level is out of the visible pane. */
private val LEVEL_DASH = PathEffect.dashPathEffect(floatArrayOf(6f, 5f))

@Composable
fun KiteStyleChart(
    candles: List<Candle>,
    levels: List<ChartLevel> = emptyList(),
    modifier: Modifier = Modifier,
) {
    if (candles.isEmpty()) return

    val total = candles.size
    val minVisible = 10

    var visibleCount by remember(total) { mutableFloatStateOf(total.toFloat()) }
    var scrollIdx by remember(total) { mutableFloatStateOf(0f) }
    var selectedIdx by remember(total) { mutableIntStateOf(-1) }

    val visInt = visibleCount.toInt().coerceIn(minVisible, total)
    val maxScroll = (total - visInt).coerceAtLeast(0)
    val startIdx = scrollIdx.roundToInt().coerceIn(0, maxScroll)
    val endIdx = min(startIdx + visInt, total)

    val visible = candles.subList(startIdx, endIdx.coerceAtMost(total))

    val scale = CandleChartMath.nicePriceScale(visible) ?: return
    val vols = CandleChartMath.volumeFractions(visible)

    // Reused across frames — Path churn is the main jank source while panning.
    val degradeLine = remember { Path() }

    val textMeasurer = rememberTextMeasurer()
    val axisStyle = remember { TextStyle(fontSize = 10.sp) }

    // Axis width computed ONCE per scale change (shared by draw + gestures so
    // crosshair snapping stays aligned with what's rendered).
    val density = LocalDensity.current
    val axisPadPx = with(density) { AXIS_PAD.toPx() }
    val axisMinPx = with(density) { AXIS_MIN_W.toPx() }
    val axisW = remember(scale) {
        val widest = scale.ticks.maxOfOrNull { tick ->
            textMeasurer.measure(CandleChartMath.formatPrice(tick, scale.decimals), axisStyle)
                .size.width
        } ?: 0
        max(widest.toFloat(), axisMinPx) + axisPadPx
    }

    Column(modifier) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(260.dp),
        ) {
            Canvas(
                Modifier
                    .fillMaxSize()
                    .pointerInput(candles.size, total, axisW) {
                        detectTapGestures(
                            onTap = { offset ->
                                val plotW = (size.width - axisW).coerceAtLeast(40f)
                                val step = plotW / max(visInt, 1)
                                selectedIdx =
                                    ((offset.x / step).toInt() + startIdx).coerceIn(0, total - 1)
                            },
                            onDoubleTap = {              // reset viewport → fit all bars
                                visibleCount = total.toFloat()
                                scrollIdx = 0f
                            },
                        )
                    }
                    .pointerInput(candles.size, total, axisW) {
                        detectTransformGestures { centroid, pan, zoom, _ ->
                            val plotW = (size.width - axisW).coerceAtLeast(40f)
                            if (abs(zoom - 1f) > 0.01f) {
                                val oldVis = visibleCount
                                visibleCount = (oldVis / zoom)
                                    .coerceIn(minVisible.toFloat(), total.toFloat())
                                val frac = (centroid.x / plotW).coerceIn(0f, 1f)
                                scrollIdx = (scrollIdx + frac * (oldVis - visibleCount))
                                    .coerceIn(0f, maxScroll.toFloat())
                            }
                            if (abs(pan.x) > 0.5f && visInt < total) {
                                scrollIdx = (scrollIdx - pan.x * visInt / plotW)
                                    .coerceIn(0f, maxScroll.toFloat())
                            }
                        }
                    },
            ) {
                drawTvChart(
                    candles = visible,
                    vols = vols,
                    scale = scale,
                    crossLocalIdx = selectedIdx
                        .takeIf { it in startIdx until endIdx }?.minus(startIdx),
                    startIdxGlobal = startIdx,
                    textMeasurer = textMeasurer,
                    axisStyle = axisStyle,
                    axisW = axisW,
                    degrade = degradeLine,
                    levels = levels,
                )
            }

            // OHLC legend — follows crosshair, defaults to latest bar
            val legendIdx = if (selectedIdx in candles.indices) selectedIdx else total - 1
            val c = candles[legendIdx]
            val prevClose = candles.getOrNull(legendIdx - 1)?.close ?: c.open
            OhlcLegend(
                o = c.open, h = c.high, l = c.low, cl = c.close,
                vol = c.volume, pctChange = (c.close - prevClose) / prevClose * 100.0,
                bullish = c.isBullish,
                Modifier.align(Alignment.TopStart).padding(8.dp),
            )

            if (visInt < total) {
                Text(
                    "${visible.size}/$total bars · pinch zoom · double-tap reset",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                    modifier = Modifier.align(Alignment.TopEnd).padding(8.dp),
                )
            }
        }

        if (visInt < total) {
            Scrollbar(
                totalBars = total,
                visibleBars = visInt,
                startIdx = startIdx,
                onScroll = { newStart ->
                    scrollIdx = newStart.toFloat().coerceIn(0f, maxScroll.toFloat())
                },
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }
    }
}

// ------------------------------------------------------------------ renderer

private fun DrawScope.drawTvChart(
    candles: List<Candle>,
    vols: List<Float>,
    scale: NicePriceScale,
    crossLocalIdx: Int?,
    startIdxGlobal: Int,
    textMeasurer: TextMeasurer,
    axisStyle: TextStyle,
    axisW: Float,
    degrade: Path,
    levels: List<ChartLevel> = emptyList(),
) {
    val w = size.width
    val h = size.height
    val n = candles.size

    // right-axis labels (width already computed in composition → axisW)
    val dec = scale.decimals
    val tickLabels = scale.ticks.map { t ->
        textMeasurer.measure(CandleChartMath.formatPrice(t, dec), axisStyle)
    }
    val plotW = (w - axisW).coerceAtLeast(40f)
    val axisPad = AXIS_PAD.toPx()

    // ---- vertical regions: price pane (+volume strip) / time axis
    val timeH = TIME_AXIS_H.toPx()
    val priceBottom = h - timeH
    val volTop = priceBottom * (1f - VOL_FRACTION)

    val pxPerBar = plotW / max(n, 1)
    val bodyW = max(pxPerBar * 0.62f, 2f)

    val sMax = scale.paddedMax
    val span = (sMax - scale.paddedMin).takeIf { it > 0 } ?: 1.0
    fun yPrice(p: Double): Float =
        (priceBottom * ((sMax - p) / span).toFloat()).coerceIn(0f, priceBottom)
    fun cx(localIdx: Int): Float = localIdx * pxPerBar + pxPerBar / 2

    // ---- price gridlines + aligned right-axis labels
    tickLabels.forEachIndexed { i, m ->
        val y = yPrice(scale.ticks[i])
        drawLine(GRID, Offset(0f, y), Offset(plotW, y), 1f)
        drawText(
            m,
            topLeft = Offset(w - axisW + (axisW - m.size.width) / 2f, y - m.size.height / 2f),
        )
    }

    // ---- time axis: non-overlapping ticks, IST day-change shows the date
    val labelGap = 36.dp.toPx()
    val tickIdxs = CandleChartMath.timeTickIndices(
        startIdxGlobal, startIdxGlobal + n, pxPerBar, labelGap,
    )
    val intraday = n < 2 ||
        (candles[min(1, n - 1)].timeMillis - candles[0].timeMillis) < 12L * 3600_000
    val timeStyle = axisStyle.copy(color = AXIS_C)
    var prevDay = -1L
    for (gi in tickIdxs) {
        val li = gi - startIdxGlobal
        if (li !in 0 until n) continue
        val ms = candles[li].timeMillis
        val istDayKey = (ms + IST_OFFSET_MS) / DAY_MS          // UTC+5:30 calendar day
        val isNewDay = istDayKey != prevDay
        prevDay = istDayKey
        val label = when {
            !intraday -> fmtDate(ms)
            isNewDay -> fmtDate(ms)
            else -> fmtTime(ms)
        }
        val x = cx(li)
        drawLine(GRID.copy(alpha = 0.6f), Offset(x, 0f), Offset(x, priceBottom), 1f)
        val m = textMeasurer.measure(label, timeStyle)
        val tx = (x - m.size.width / 2f).coerceIn(0f, plotW - m.size.width)
        drawText(m, topLeft = Offset(tx, h - timeH + (timeH - m.size.height) / 2f))
    }

    // axis divider
    drawLine(GRID, Offset(plotW, 0f), Offset(plotW, h - timeH), 1f)

    val degenerate = pxPerBar < DEGRADE_PX_PER_BAR

    if (!degenerate) {
        // volume behind price
        val volMaxH = priceBottom - volTop
        for (i in 0 until n) {
            val frac = vols.getOrNull(i) ?: continue
            val bh = volMaxH * frac
            if (bh <= 0f) continue
            drawRect(
                (if (candles[i].isBullish) BULL else BEAR).copy(alpha = .30f),
                Offset(cx(i) - bodyW / 2, priceBottom - bh),
                Size(bodyW, bh),
            )
        }
        // candles: wick + body in one pass
        for (i in 0 until n) {
            val c = candles[i]
            val x = cx(i)
            val color = if (c.isBullish) BULL else BEAR
            drawLine(color, Offset(x, yPrice(c.high)), Offset(x, yPrice(c.low)), 2f)
            val top = yPrice(maxOf(c.open, c.close))
            val bot = yPrice(minOf(c.open, c.close))
            drawRoundRect(
                color,
                Offset(x - bodyW / 2, top),
                Size(bodyW, (bot - top).coerceAtLeast(2f)),
                CornerRadius(2f, 2f),
            )
        }
    } else {
        // extreme zoom-out → close polyline keeps the shape readable
        degrade.reset()
        var started = false
        for (i in 0 until n) {
            val y = yPrice(candles[i].close)
            if (!started) { degrade.moveTo(cx(i), y); started = true }
            else degrade.lineTo(cx(i), y)
        }
        drawPath(degrade, LINE_C, style = Stroke(2f, cap = StrokeCap.Round))
    }

    // ---- last close pinned on the axis (dotted level + direction tag)
    val last = candles[n - 1]
    val lastY = yPrice(last.close)
    val lastColor = if (last.isBullish) BULL else BEAR
    drawLine(
        lastColor, Offset(0f, lastY), Offset(plotW, lastY), 1.5f,
        pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 5f)),
    )
    drawTag(
        CandleChartMath.formatPrice(last.close, dec),
        left = plotW + 1f, width = w - plotW - 2f, centerY = lastY,
        bg = lastColor, fg = TAG_TEXT, textMeasurer = textMeasurer,
        style = axisStyle, pad = axisPad,
    )

    // ---- pattern levels (dashed horizontal lines + axis tags)
    levels.forEach { lv ->
        val lvColor = when {
            lv.tag.startsWith("SL", ignoreCase = true) -> BEAR
            lv.tag.startsWith("T", ignoreCase = true) -> BULL
            else -> CROSS
        }
        val y = yPrice(lv.price)
        if (y in 0f..priceBottom) {
            drawLine(lvColor, Offset(0f, y), Offset(plotW, y), 1.2f,
                pathEffect = LEVEL_DASH)
            drawTag(
                lv.tag,
                left = plotW + 1f, width = w - plotW - 2f, centerY = y,
                bg = lvColor, fg = TAG_TEXT, textMeasurer = textMeasurer,
                style = axisStyle, pad = axisPad,
            )
        }
    }

    // ---- magnet crosshair spanning all panes + price/time tags
    crossLocalIdx?.let { ci ->
        val x = cx(ci)
        drawLine(CROSS.copy(.7f), Offset(x, 0f), Offset(x, h - timeH), 1.5f)
        val c = candles.getOrNull(ci) ?: return@let
        val cy = yPrice(c.close)
        drawLine(CROSS.copy(.5f), Offset(0f, cy), Offset(plotW, cy), 1f)
        drawTag(
            CandleChartMath.formatPrice(c.close, dec),
            left = plotW + 1f, width = w - plotW - 2f, centerY = cy,
            bg = CROSS, fg = TAG_TEXT_DARK, textMeasurer = textMeasurer,
            style = axisStyle, pad = axisPad,
        )
        val tm = textMeasurer.measure(fmtTime(c.timeMillis), axisStyle.copy(color = TAG_TEXT_DARK))
        val tw = tm.size.width + 2 * axisPad
        val tLeft = (x - tw / 2).coerceIn(0f, plotW - tw)
        val tTop = h - timeH + 1f
        drawRoundRect(CROSS, Offset(tLeft, tTop), Size(tw, timeH - 2f), CornerRadius(4f, 4f))
        drawText(
            tm,
            topLeft = Offset(
                tLeft + (tw - tm.size.width) / 2f,
                tTop + (timeH - 2f - tm.size.height) / 2f,
            ),
        )
    }
}

/** Rounded full-height tag on the axis column, centred vertically at centerY. */
private fun DrawScope.drawTag(
    text: String,
    left: Float,
    width: Float,
    centerY: Float,
    bg: Color,
    fg: Color,
    textMeasurer: TextMeasurer,
    style: TextStyle,
    pad: Float,
) {
    val m = textMeasurer.measure(text, style.copy(color = fg))
    val tagH = m.size.height + pad
    drawRoundRect(bg, Offset(left, centerY - tagH / 2), Size(width, tagH), CornerRadius(4f, 4f))
    drawText(
        m,
        topLeft = Offset(left + (width - m.size.width) / 2f, centerY - m.size.height / 2f),
    )
}

// ------------------------------------------------------------------ legend

@Composable
private fun OhlcLegend(
    o: Double, h: Double, l: Double, cl: Double, vol: Long,
    pctChange: Double, bullish: Boolean,
    modifier: Modifier = Modifier,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color(0xE6121821)),
        shape = RoundedCornerShape(6.dp),
        modifier = modifier,
    ) {
        val chgColor = if (bullish) BULL else BEAR
        val sign = if (pctChange >= 0) "+" else ""
        Column(Modifier.padding(horizontal = 8.dp, vertical = 6.dp)) {
            Text(
                "O %.2f  H %.2f  L %.2f  C %.2f".format(o, h, l, cl),
                style = MaterialTheme.typography.labelSmall,
                color = chgColor,
            )
            Spacer(Modifier.height(1.dp))
            Text(
                "V $vol   $sign${"%.2f".format(abs(pctChange))}%",
                style = MaterialTheme.typography.labelSmall,
                color = chgColor.copy(alpha = 0.85f),
            )
        }
    }
}

// ------------------------------------------------------------------ time fmt

private const val IST_OFFSET_MS = 19_800_000L     // UTC+5:30
private const val DAY_MS = 86_400_000L

private val timeFmt = SimpleDateFormat("HH:mm", Locale.getDefault())
private val dateFmt = SimpleDateFormat("dd MMM", Locale.getDefault())

private fun fmtTime(ms: Long): String = timeFmt.format(Date(ms))
private fun fmtDate(ms: Long): String = dateFmt.format(Date(ms))

// ------------------------------------------------------------------ scrollbar

@Composable
private fun Scrollbar(
    totalBars: Int,
    visibleBars: Int,
    startIdx: Int,
    onScroll: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    BoxWithConstraints(modifier.height(8.dp)) {
        val trackW = constraints.maxWidth.toFloat().coerceAtLeast(1f)
        val maxScroll = (totalBars - visibleBars).coerceAtLeast(0)
        val thumbW = trackW * visibleBars / totalBars
        val thumbX = trackW * startIdx / totalBars
        val density = LocalDensity.current
        val thumbWidthDp = with(density) { thumbW.toDp() }

        fun seek(x: Float) {
            val target = (x - thumbW / 2) / trackW * totalBars - visibleBars / 2f
            onScroll(target.roundToInt().coerceIn(0, maxScroll))
        }

        Box(
            Modifier
                .fillMaxSize()
                .clip(RoundedCornerShape(4.dp))
                .background(GRID.copy(alpha = 0.5f)),
        )
        Box(
            Modifier
                .offset { IntOffset(thumbX.roundToInt(), 0) }
                .width(thumbWidthDp)
                .fillMaxHeight()
                .clip(RoundedCornerShape(4.dp))
                .background(CROSS.copy(alpha = 0.55f)),
        )
        Box(
            Modifier
                .fillMaxSize()
                .pointerInput(totalBars, visibleBars) {
                    detectDragGestures(
                        onDragStart = { off -> seek(off.x) },
                        onDrag = { change, _ ->
                            change.consume()
                            seek(change.position.x)
                        },
                    )
                },
        )
    }
}
