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
private val BB_FILL = Color(0x154E9CFF)
private val SMA20_C = Color(0xFFFF9800)
private val EMA9_C = Color(0xFFE040FB)
private val PANE_BG = Color(0xFF0D1117)
private val TAG_TEXT = Color(0xFFFFFFFF)
private val TAG_TEXT_DARK = Color(0xFF0B1420)

// Geometry constants (lightweight-charts-inspired layout)
private val TIME_AXIS_H = 22.dp
private val PANE_GAP = 4.dp
private val RSI_PANE_H = 56.dp
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
 *  • volume overlaid behind price; RSI pane shares the same crosshair
 *  • degrades to a close-line when bars drop below [DEGRADE_PX_PER_BAR] px
 */
@Composable
fun KiteStyleChart(
    candles: List<Candle>,
    showSma20: Boolean,
    showEma9: Boolean,
    showBb: Boolean,
    showRsi: Boolean,
    modifier: Modifier = Modifier,
    sma20Values: List<Double?>? = null,
    ema9Values: List<Double?>? = null,
    bbUpper: List<Double?>? = null,
    bbLower: List<Double?>? = null,
    rsiValues: List<Double?>? = null,
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
    val visSma20 = sma20Values?.subList(startIdx, endIdx.coerceAtMost(sma20Values.size))
    val visEma9 = ema9Values?.subList(startIdx, endIdx.coerceAtMost(ema9Values.size))
    val visBbU = bbUpper?.subList(startIdx, endIdx.coerceAtMost(bbUpper.size))
    val visBbL = bbLower?.subList(startIdx, endIdx.coerceAtMost(bbLower.size))
    val visRsi = rsiValues?.subList(startIdx, endIdx.coerceAtMost(rsiValues.size))

    val scale = CandleChartMath.nicePriceScale(visible) ?: return
    val vols = CandleChartMath.volumeFractions(visible)

    // Reused across frames — Path churn is the main jank source while panning.
    val bbUpPath = remember { Path() }
    val bbLoPath = remember { Path() }
    val smaPath = remember { Path() }
    val emaPath = remember { Path() }
    val rsiPath = remember { Path() }
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
                .height(if (showRsi && visRsi != null) 300.dp else 260.dp),
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
                    bbU = if (showBb) visBbU else null,
                    bbL = if (showBb) visBbL else null,
                    sma = if (showSma20) visSma20 else null,
                    ema = if (showEma9) visEma9 else null,
                    rsi = if (showRsi) visRsi else null,
                    crossLocalIdx = selectedIdx
                        .takeIf { it in startIdx until endIdx }?.minus(startIdx),
                    startIdxGlobal = startIdx,
                    textMeasurer = textMeasurer,
                    axisStyle = axisStyle,
                    axisW = axisW,
                    paths = OverlayPaths(bbUpPath, bbLoPath, smaPath, emaPath, rsiPath, degradeLine),
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

private class OverlayPaths(
    val bbUp: Path,
    val bbLo: Path,
    val sma: Path,
    val ema: Path,
    val rsi: Path,
    val degrade: Path,
)

private fun DrawScope.drawTvChart(
    candles: List<Candle>,
    vols: List<Float>,
    scale: NicePriceScale,
    bbU: List<Double?>?,
    bbL: List<Double?>?,
    sma: List<Double?>?,
    ema: List<Double?>?,
    rsi: List<Double?>?,
    crossLocalIdx: Int?,
    startIdxGlobal: Int,
    textMeasurer: TextMeasurer,
    axisStyle: TextStyle,
    axisW: Float,
    paths: OverlayPaths,
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

    // ---- vertical regions: price pane (+volume strip) / RSI pane / time axis
    val timeH = TIME_AXIS_H.toPx()
    val hasRsi = rsi != null && rsi.any { it != null }
    val gap = PANE_GAP.toPx()
    val rsiH = if (hasRsi) RSI_PANE_H.toPx() else 0f
    val priceBottom = h - timeH - (if (hasRsi) rsiH + gap else 0f)
    val volTop = priceBottom * (1f - VOL_FRACTION)

    val pxPerBar = plotW / max(n, 1)
    val bodyW = max(pxPerBar * 0.62f, 2f)

    val sMax = scale.paddedMax
    val span = (sMax - scale.paddedMin).takeIf { it > 0 } ?: 1.0
    fun yPrice(p: Double): Float =
        (priceBottom * ((sMax - p) / span).toFloat()).coerceIn(0f, priceBottom)
    fun cx(localIdx: Int): Float = localIdx * pxPerBar + pxPerBar / 2

    fun overlayLine(values: List<Double?>, path: Path, color: Color, strokeW: Float) {
        if (values.all { it == null }) return
        path.reset()
        var started = false
        for (i in values.indices) {
            values[i]?.let { v ->
                val y = yPrice(v)
                if (!started) { path.moveTo(cx(i), y); started = true } else path.lineTo(cx(i), y)
            } ?: run { started = false }
        }
        drawPath(path, color, style = Stroke(strokeW, cap = StrokeCap.Round))
    }

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

    // ---- Bollinger bands (fill behind, thin outlines)
    if (bbU != null && bbL != null) {
        paths.bbUp.reset(); paths.bbLo.reset()
        var uStarted = false; var lStarted = false
        for (i in 0 until n) {
            val x = cx(i)
            bbU.getOrNull(i)?.let { v ->
                val y = yPrice(v)
                if (!uStarted) { paths.bbUp.moveTo(x, y); uStarted = true } else paths.bbUp.lineTo(x, y)
            }
            bbL.getOrNull(i)?.let { v ->
                val y = yPrice(v)
                if (!lStarted) { paths.bbLo.moveTo(x, y); lStarted = true } else paths.bbLo.lineTo(x, y)
            }
        }
        if (uStarted && lStarted) {
            for (i in n - 1 downTo 0) {
                bbL.getOrNull(i)?.let { v -> paths.bbLo.lineTo(cx(i), yPrice(v)) }
            }
            paths.bbUp.addPath(paths.bbLo)
            paths.bbUp.close()
            drawPath(paths.bbUp, BB_FILL)
        }
        overlayLine(bbU, paths.bbUp, LINE_C.copy(alpha = .5f), 1.5f)
        overlayLine(bbL, paths.bbLo, LINE_C.copy(alpha = .5f), 1.5f)
    }

    val degrade = pxPerBar < DEGRADE_PX_PER_BAR

    if (!degrade) {
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
        paths.degrade.reset()
        var started = false
        for (i in 0 until n) {
            val y = yPrice(candles[i].close)
            if (!started) { paths.degrade.moveTo(cx(i), y); started = true }
            else paths.degrade.lineTo(cx(i), y)
        }
        drawPath(paths.degrade, LINE_C, style = Stroke(2f, cap = StrokeCap.Round))
    }

    if (sma != null) overlayLine(sma, paths.sma, SMA20_C, 2f)
    if (ema != null) overlayLine(ema, paths.ema, EMA9_C, 2f)

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

    // ---- RSI pane sharing the crosshair
    if (hasRsi && rsi != null) {
        val rsiTop = priceBottom + gap
        drawRect(PANE_BG, Offset(0f, rsiTop), Size(plotW, rsiH))
        fun yRsi(v: Double): Float = rsiTop + rsiH * (1f - v.toFloat() / 100f)
        listOf(30.0, 70.0).forEach { lvl ->
            val y = yRsi(lvl)
            drawLine(GRID, Offset(0f, y), Offset(plotW, y), 1f)
            val lm = textMeasurer.measure("${lvl.toInt()}", axisStyle.copy(color = AXIS_C))
            drawText(
                lm,
                topLeft = Offset(w - axisW + (axisW - lm.size.width) / 2f, y - lm.size.height / 2f),
            )
        }
        paths.rsi.reset()
        var started = false
        for (i in 0 until n) {
            rsi.getOrNull(i)?.let { v ->
                val y = yRsi(v)
                if (!started) { paths.rsi.moveTo(cx(i), y); started = true }
                else paths.rsi.lineTo(cx(i), y)
            } ?: run { started = false }
        }
        drawPath(paths.rsi, LINE_C, style = Stroke(1.8f, cap = StrokeCap.Round))
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

object ChartColors {
    val SMA20 = SMA20_C
    val EMA9 = EMA9_C
    val BB = LINE_C
    val SMA50 = Color(0xFFAB47BC)
}
