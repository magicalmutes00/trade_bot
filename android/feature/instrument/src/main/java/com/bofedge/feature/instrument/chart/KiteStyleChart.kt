package com.bofedge.feature.instrument.chart

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import com.bofedge.domain.model.Candle
import androidx.compose.ui.draw.clip
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.roundToInt
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.shape.RoundedCornerShape
import kotlin.math.max

private val BULL = Color(0xFF16C784)
private val BEAR = Color(0xFFEA3943)
private val GRID = Color(0xFF1A2230)
private val CROSS = Color(0xFF4E9CFF)
private val AXIS_C = Color(0xFF8A97A8)
private val LINE_C = Color(0xFF4E9CFF)
private val BB_FILL = Color(0x154E9CFF)
private val SMA20_C = Color(0xFFFF9800)
private val EMA9_C = Color(0xFFE040FB)

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
    val startIdx = scrollIdx

        .roundToInt().coerceIn(0, maxScroll)
    val endIdx = min(startIdx + visInt, total)

    val visible = candles.subList(startIdx, endIdx.coerceAtMost(total))
    val visSma20 = sma20Values?.subList(startIdx, endIdx.coerceAtMost(sma20Values.size))
    val visEma9 = ema9Values?.subList(startIdx, endIdx.coerceAtMost(ema9Values.size))
    val visBbU = bbUpper?.subList(startIdx, endIdx.coerceAtMost(bbUpper.size))
    val visBbL = bbLower?.subList(startIdx, endIdx.coerceAtMost(bbLower.size))
    val visRsi = rsiValues?.subList(startIdx, endIdx.coerceAtMost(rsiValues.size))

    val scale = CandleChartMath.priceScale(visible) ?: return
    val vols = CandleChartMath.volumeFractions(visible)

    Column(modifier) {
        // ---- main price chart ----
        Row(Modifier.fillMaxWidth()) {
            Box(Modifier.weight(1f).height(if (showRsi) 200.dp else 240.dp)) {
                Canvas(
                    Modifier
                        .fillMaxSize()
                        .pointerInput(candles.size) {
                            detectTapGestures { offset ->
                                val step = size.width / max(visInt, 1)
                                selectedIdx =
                                    ((offset.x / step).toInt() + startIdx).coerceIn(0, total - 1)
                            }
                        }
                        .pointerInput(candles.size, total) {
                            detectTransformGestures { centroid, pan, zoom, _ ->
                                if (abs(zoom - 1f) > 0.01f) {
                                    val oldVis = visibleCount
                                    visibleCount = (oldVis / zoom)
                                        .coerceIn(minVisible.toFloat(), total.toFloat())
                                    val frac = (centroid.x / size.width).coerceIn(0f, 1f)
                                    scrollIdx = (scrollIdx + frac * (oldVis - visibleCount))
                                        .coerceIn(0f, maxScroll.toFloat())
                                }
                                if (abs(pan.x) > 0.5f && visInt < total) {
                                    val pxPerBar = size.width / visInt
                                    scrollIdx = (scrollIdx - pan.x / pxPerBar)
                                        .coerceIn(0f, maxScroll.toFloat())
                                }
                            }
                        },
                ) {
                    drawChart(
                        candles = visible,
                        paddedMin = scale.paddedMin,
                        paddedMax = scale.paddedMax,
                        vols = vols,
                        w = size.width,
                        priceH = if (showRsi) size.height * 0.82f else size.height * 0.84f,
                        volTop = if (showRsi) size.height * 0.82f + 8f else size.height * 0.84f + 8f,
                        volMaxH = size.height - (if (showRsi) size.height * 0.82f + 8f else size.height * 0.84f + 8f) - 4f,
                        showBb = showBb,
                        bbU = visBbU,
                        bbL = visBbL,
                        sma20 = if (showSma20) visSma20 else null,
                        ema9 = if (showEma9) visEma9 else null,
                        crosshairIdx = selectedIdx.takeIf { it in startIdx until endIdx }?.minus(startIdx),
                    )
                }

                // OHLC tooltip
                if (selectedIdx in startIdx until endIdx) {
                    val c = candles[selectedIdx]
                    OhlcTooltip(
                        o = c.open, h = c.high, l = c.low, cl = c.close, vol = c.volume,
                        Modifier.align(Alignment.TopStart).padding(8.dp),
                    )
                }

                // "zoomed" indicator
                if (visInt < total) {
                    Text(
                        "${visible.size}/${total} bars",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                        modifier = Modifier.align(Alignment.TopEnd).padding(8.dp),
                    )
                }
            }

            // price axis
            Column(
                Modifier.fillMaxHeight().width(52.dp),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                AxisText("%.0f".format(scale.paddedMax))
                AxisText("%.0f".format((scale.paddedMax + scale.paddedMin) / 2))
                AxisText("%.0f".format(scale.paddedMin))
            }
        }

        // ---- RSI sub-panel ----
        if (showRsi && visRsi != null) {
            RsiPanel(visRsi, visible, Modifier.fillMaxWidth().height(80.dp))
        }

        // ---- Horizontal scrollbar ----
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

// ------------------------------------------------------------------ canvas

private fun DrawScope.drawChart(
    candles: List<Candle>,
    paddedMin: Double, paddedMax: Double,
    vols: List<Float>,
    w: Float,
    priceH: Float,
    volTop: Float,
    volMaxH: Float,
    showBb: Boolean,
    bbU: List<Double?>?,
    bbL: List<Double?>?,
    sma20: List<Double?>?,
    ema9: List<Double?>?,
    crosshairIdx: Int?,
) {
    fun yPrice(p: Double): Float = priceH * (((paddedMax - p) / (paddedMax - paddedMin)).toFloat().coerceIn(0f, 1f))

    // grid
    val mid = paddedMin + (paddedMax - paddedMin) / 2
    listOf(paddedMin, mid, paddedMax).forEach { level ->
        drawLine(GRID, Offset(0f, yPrice(level)), Offset(w, yPrice(level)), 1f)
    }

    val n = candles.size
    val step = w / max(n, 1)
    val bodyW = max(step * 0.62f, 2f)

    // BB fill
    if (showBb && bbU != null && bbL != null) {
        val upPath = Path(); val loPath = Path()
        var uS = false; var lS = false
        for (i in 0 until n) {
            val x = step * i + step / 2
            bbU.getOrNull(i)?.let { v -> val y = yPrice(v); if (!uS) { upPath.moveTo(x, y); uS = true } else upPath.lineTo(x, y) }
            bbL.getOrNull(i)?.let { v -> val y = yPrice(v); if (!lS) { loPath.moveTo(x, y); lS = true } else loPath.lineTo(x, y) }
        }
        if (uS && lS) {
            for (i in n - 1 downTo 0) {
                bbL.getOrNull(i)?.let { v -> loPath.lineTo(step * i + step / 2, yPrice(v)) }
            }
            upPath.close()
            drawPath(upPath, BB_FILL)
        }
    }

    // volume
    candles.forEachIndexed { i, c ->
        vols.getOrNull(i)?.let { frac ->
            val h = volMaxH * frac
            drawRect(
                if (c.isBullish) BULL.copy(alpha = .35f) else BEAR.copy(alpha = .35f),
                Offset(step*i+step/2-bodyW/2, volTop+(volMaxH-h)), Size(bodyW,h))
        }
    }

    // candle bodies + wicks
    candles.forEachIndexed { i, c ->
        val cx = step*i+step/2
        val color = if (c.isBullish) BULL else BEAR
        drawLine(color, Offset(cx,yPrice(c.high)), Offset(cx,yPrice(c.low)), 2f)
        val top=yPrice(maxOf(c.open,c.close))
        val bot=yPrice(minOf(c.open,c.close))
        drawRoundRect(color, Offset(cx-bodyW/2,top), Size(bodyW,(bot-top).coerceAtLeast(2f)),
            CornerRadius(2f,2f))
    }

    // indicator overlays
    fun overlay(values: List<Double?>?, color: Color, width_: Float = 2f) {
        if (values == null || values.size < n) return
        val p = Path(); var started = false
        for (i in 0 until n) {
            values.getOrNull(i)?.let { v ->
                val x=step*i+step/2; val y=yPrice(v)
                if(!started){p.moveTo(x,y);started=true} else p.lineTo(x,y)
            } ?: run { started=false }
        }
        drawPath(p, color, style=Stroke(width_, cap=StrokeCap.Round))
    }

    if (showBb && bbU != null) overlay(bbU, LINE_C.copy(alpha=.5f), 1.5f)
    if (showBb && bbL != null) overlay(bbL, LINE_C.copy(alpha=.5f), 1.5f)
    if (sma20 != null) overlay(sma20, SMA20_C, 2f)
    if (ema9 != null) overlay(ema9, EMA9_C, 2f)

    // crosshair
    crosshairIdx?.let { ci ->
        val cx = step*ci+step/2
        drawLine(CROSS.copy(.7f), Offset(cx,0f), Offset(cx,priceH), 1.5f)
        candles.getOrNull(ci)?.let { c ->
            val cy = yPrice(c.close)
            drawLine(CROSS.copy(.5f), Offset(0f,cy), Offset(w,cy), 1f)
        }
    }
}

// ------------------------------------------------------------------ RSI panel

@Composable
private fun RsiPanel(values: List<Double?>, candles: List<Candle>, modifier: Modifier = Modifier) {
    Box(modifier.background(Color(0xFF0D1117))) {
        Canvas(Modifier.fillMaxSize()) {
            val w = size.width; val h = size.height
            listOf(30f, 70f).forEach { pct ->
                val y = h * (1f - pct / 100f)
                drawLine(GRID, Offset(0f, y), Offset(w, y), 1f)
            }
            val path = Path(); var started = false
            val step = w / max(candles.size, 1)
            candles.forEachIndexed { i, _ ->
                values.getOrNull(i)?.let { v ->
                    val x = step*i+step/2; val y = h*(1f-v.toFloat()/100f)
                    if(!started){path.moveTo(x,y);started=true}else path.lineTo(x,y)
                } ?: run { started=false }
            }
            drawPath(path, LINE_C, style=Stroke(2f))
        }
        Column(Modifier.padding(start=8.dp, top=4.dp)) {
            Text("RSI 14", style=MaterialTheme.typography.labelSmall, color=CROSS)
            Text("70 ───", style=MaterialTheme.typography.labelSmall, color=AXIS_C)
        }
    }
}

// ------------------------------------------------------------------ tooltip

@Composable
private fun OhlcTooltip(o: Double, h: Double, l: Double, cl: Double, vol: Long,
                        modifier: Modifier = Modifier) {
    val oS = "%.2f".format(o); val hS = "%.2f".format(h)
    val lS = "%.2f".format(l); val cS = "%.2f".format(cl)
    Card(colors = CardDefaults.cardColors(containerColor = Color(0xE6121821)),
         shape = MaterialTheme.shapes.small, modifier = modifier) {
        Column(Modifier.padding(8.dp)) {
            Text("O $oS  H $hS", style = MaterialTheme.typography.labelSmall, color = BULL)
            Text("L $lS  C $cS", style = MaterialTheme.typography.labelSmall, color = BEAR)
            Text("V $vol", style = MaterialTheme.typography.labelSmall, color = AXIS_C)
        }
    }
}

// ------------------------------------------------------------------ axis text

@Composable
private fun AxisText(value: String, modifier: Modifier = Modifier) {
    Text(value, style = MaterialTheme.typography.labelSmall, color = AXIS_C, modifier = modifier)
}

// ------------------------------------------------------------------ scrollbar

@Composable
private fun Scrollbar(
    totalBars: Int,
    visibleBars: Int,
    startIdx: Int,
    onScroll: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val maxScroll = (totalBars - visibleBars).coerceAtLeast(0)
    val thumbFraction = visibleBars.toFloat() / totalBars
    val thumbOffsetFraction = if (maxScroll > 0) startIdx.toFloat() / maxScroll else 0f

    Box(
        modifier
            .height(6.dp)
            .clip(androidx.compose.foundation.shape.RoundedCornerShape(3.dp))
            .background(GRID.copy(alpha = 0.5f))
            .pointerInput(totalBars, visibleBars) {
                detectDragGestures(
                    onDragStart = { offset ->
                        val frac = offset.x / size.width
                        onScroll((frac * maxScroll).roundToInt())
                    },
                    onDrag = { change, _ ->
                        change.consume()
                        val deltaFrac = change.position.x / size.width
                        val deltaBars = (deltaFrac * maxScroll).roundToInt()
                        onScroll((startIdx + deltaBars).coerceIn(0, maxScroll))
                    },
                )
            },
    ) {
        Box(
            Modifier
                .fillMaxHeight()
                .fillMaxWidth(thumbFraction)
                .align(Alignment.CenterStart)
                .offset(x = (thumbOffsetFraction * (1f / thumbFraction) * 100).dp)
                .clip(androidx.compose.foundation.shape.RoundedCornerShape(3.dp))
                .background(CROSS.copy(alpha = 0.55f)),
        )
    }
}







object ChartColors {
    val SMA20 = SMA20_C
    val EMA9 = EMA9_C
    val BB = LINE_C
    val SMA50 = Color(0xFFAB47BC)
}
