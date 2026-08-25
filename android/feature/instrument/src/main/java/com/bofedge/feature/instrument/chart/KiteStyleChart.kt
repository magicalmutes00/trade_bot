package com.bofedge.feature.instrument.chart

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
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
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

private val BULL = Color(0xFF16C784)
private val BEAR = Color(0xFFEA3943)
private val GRID = Color(0xFF1A2230)
private val CROSS = Color(0xFF4E9CFF)
private val AXIS_C = Color(0xFF8A97A8)
private val LINE_COLOR = Color(0xFF4E9CFF)
private val BB_FILL = Color(0x154E9CFF)
private val SMA20_C = Color(0xFFFF9800)
private val EMA9_C = Color(0xFFE040FB)

/**
 * Kite/Upstox-style candlestick chart with pinch-to-zoom, horizontal pan,
 * crosshair tooltip and indicator overlays.
 *
 * Gestures:
 *   Pinch    → zoom in/out (changes number of visible candles)
 *   Drag     → pan horizontally through history when zoomed in
 *   Tap      → show crosshair + OHLC tooltip at tapped bar
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

    // ---- viewport state ----
    var visibleCount by remember(total) {
        androidx.compose.runtime.mutableFloatStateOf(total.toFloat())
    }
    var scrollIndex by remember(total) {
        androidx.compose.runtime.mutableFloatStateOf((total - total.toFloat()).coerceAtLeast(0f).let { 0f })
    } // always starts showing latest bars
    var selectedIndex by remember { mutableIntStateOf(-1) }

    // compute visible slice
    val visInt = visibleCount.toInt().coerceIn(minVisible, total)
    val maxScroll = (total - visInt).coerceAtLeast(0)
    val startIdx = scrollIndex.roundToInt().coerceIn(0, maxScroll)
    val endIdx = (startIdx + visInt).coerceIn(startIdx + minVisible, total)

    val visible = candles.subList(startIdx, endIdx.coerceAtMost(total))
    val visibleSma20 = sma20Values?.subList(startIdx, endIdx.coerceAtMost(sma20Values.size))
    val visibleEma9 = ema9Values?.subList(startIdx, endIdx.coerceAtMost(ema9Values.size))
    val visibleBbU = bbUpper?.subList(startIdx, endIdx.coerceAtMost(bbUpper.size))
    val visibleBbL = bbLower?.subList(startIdx, endIdx.coerceAtMost(bbLower.size))
    val visibleRsi = rsiValues?.subList(startIdx, endIdx.coerceAtMost(rsiValues.size))

    val scale = CandleChartMath.priceScale(visible) ?: return
    val vols = CandleChartMath.volumeFractions(visible)

    Column(modifier) {
        // ---- Main price chart ----
        Row(Modifier.fillMaxWidth()) {
            Box(Modifier.weight(1f).height(if (showRsi) 200.dp else 240.dp)) {
                Canvas(
                    Modifier
                        .fillMaxSize()
                        .pointerInput(candles.size) {
                            detectTapGestures { offset ->
                                val step = size.width / max(visInt, 1)
                                val idx = (offset.x / step).toInt() + startIdx
                                selectedIndex = idx.coerceIn(0, total - 1)
                            }
                        }
                        .pointerInput(candles.size, total) {
                            detectTransformGestures { centroid, pan, zoom, _ ->
                                // --- pinch zoom ---
                                if (abs(zoom - 1f) > 0.01f) {
                                    val old = visibleCount
                                    val newVis = (old / zoom)
                                        .coerceIn(minVisible.toFloat(), total.toFloat())
                                    // keep centroid anchored
                                    val frac = (centroid.x / size.width).coerceIn(0f, 1f)
                                    val oldStart = scrollIndex
                                    scrollIndex =
                                        (oldStart + frac * (old - newVis)).coerceIn(0f, maxScroll.toFloat())
                                    visibleCount = newVis
                                }
                                // --- horizontal pan ---
                                if (abs(pan.x) > 0.5f && visInt < total) {
                                    val stepPx = size.width / visInt
                                    val shift = pan.x / stepPx
                                    scrollIndex = (scrollIndex - shift)
                                        .coerceIn(0f, maxScroll.toFloat())
                                }
                            }
                        },
                ) {
                    val w = size.width
                    val priceH = if (showRsi) size.height * 0.82f else size.height * 0.84f
                    val volTop = priceH + 8f
                    val volMaxH = size.height - volTop - 4f

                    fun yPrice(p: Double): Float =
                        priceH * CandleChartMath.yFraction(p, scale)

                    // grid lines
                    scale.gridLines.forEach { level ->
                        drawLine(GRID, Offset(0f, yPrice(level)), Offset(w, yPrice(level)), 1f)
                    }

                    val n = visible.size
                    val step = w / max(n, 1)
                    val bodyW = max(step * 0.62f, 2f)

                    // Bollinger band fill
                    if (showBb && visibleBbU != null && visibleBbL != null) {
                        drawBandFill(n, visibleBbU, visibleBbL, ::yPrice, step)
                    }

                    // volume bars
                    vols.forEachIndexed { i, frac ->
                        val h = volMaxH * frac
                        val c = visible[i]
                        val col = if (c.isBullish) BULL.copy(alpha = 0.35f)
                                  else BEAR.copy(alpha = 0.35f)
                        drawRect(col,
                            Offset(step*i+step/2-bodyW/2, volTop+(volMaxH-h)),
                            Size(bodyW, h))
                    }

                    // candle bodies + wicks
                    visible.forEachIndexed { i, c ->
                        val cx = step*i+step/2
                        val color = if (c.isBullish) BULL else BEAR
                        drawLine(color, Offset(cx,yPrice(c.high)), Offset(cx,yPrice(c.low)), 2f)
                        val top=yPrice(maxOf(c.open,c.close))
                        val bot=yPrice(minOf(c.open,c.close))
                        drawRoundRect(color, Offset(cx-bodyW/2,top),
                            Size(bodyW,(bot-top).coerceAtLeast(2f)), CornerRadius(2f,2f))
                    }

                    // indicator overlays
                    fun lineOverlay(values: List<Double?>?, color: Color, width_: Float = 2.5f) {
                        if (values == null || values.size < n) return
                        val p = Path(); var started=false
                        for (i in 0 until n) {
                            values.getOrNull(i)?.let { v ->
                                val x=step*i+step/2; val y=yPrice(v)
                                if(!started){p.moveTo(x,y);started=true} else p.lineTo(x,y)
                            } ?: run { started=false }
                        }
                        drawPath(p, color, style=Stroke(width_, cap=StrokeCap.Round))
                    }

                    if (showBb) {
                        lineOverlay(visibleBbU, LINE_COLOR.copy(alpha=.6f), 1.5f)
                        lineOverlay(visibleBbL, LINE_COLOR.copy(alpha=.6f), 1.5f)
                    }
                    if (showSma20) lineOverlay(visibleSma20, SMA20_C, 2f)
                    if (showEma9) lineOverlay(visibleEma9, EMA9_C, 2f)

                    // crosshair
                    if (selectedIndex >= startIdx && selectedIndex < endIdx && selectedIndex < total) {
                        val relIdx = selectedIndex - startIdx
                        val cx = step*relIdx+step/2
                        drawLine(CROSS.copy(.7f), Offset(cx,0f), Offset(cx,priceH), 1.5f)
                        val cy = yPrice(visible.getOrNull(relIdx)?.close ?: return@Canvas)
                        drawLine(CROSS.copy(.5f), Offset(0f,cy), Offset(w,cy), 1f)
                    }
                }

                // OHLC tooltip overlay
                if (selectedIndex >= 0 && selectedIndex < total &&
                    selectedIndex >= startIdx && selectedIndex < endIdx) {
                    val c = candles[selectedIndex]
                    TooltipCard(
                        o=c.open, h=c.high, l=c.low, cl=c.close, vol=c.volume,
                        Modifier.align(Alignment.TopStart).padding(8.dp),
                    )
                }
            }

            // price axis
            Column(
                Modifier.fillMaxHeight().width(52.dp),
                verticalArrangement = Arrangement.SpaceBetween,
            ) {
                AxisText("%.0f".format(scale.paddedMax))
                AxisText("%.0f".format((scale.paddedMax+scale.paddedMin)/2))
                AxisText("%.0f".format(scale.paddedMin))
            }
        }

        // ---- RSI sub-panel ----
        if (showRsi && visibleRsi != null) {
            RsiPanel(visibleRsi, visible, Modifier.fillMaxWidth().height(80.dp))
        }
    }
}

// ------------------------------------------------------------------ layers

private fun DrawScope.drawBandFill(
    count: Int, upper: List<Double?>, lower: List<Double?>,
    yPrice: (Double)->Float, step: Float,
) {
    val upPath = Path(); val loPath = Path()
    var uStarted=false; var lStarted=false
    for(i in 0 until count){
        val x=step*i+step/2
        upper.getOrNull(i)?.let{v->val y=yPrice(v);if(!uStarted){upPath.moveTo(x,y);uStarted=true}else upPath.lineTo(x,y)}
        lower.getOrNull(i)?.let{v->val y=yPrice(v);if(!lStarted){loPath.moveTo(x,y);lStarted=true}else loPath.lineTo(x,y)}
    }
    if(uStarted&&lStarted){
        for(i in count-1 downTo 0){
            lower.getOrNull(i)?.let{v->loPath.lineTo(step*i+step/2,yPrice(v))}
        }
        upPath.close()
        drawPath(upPath,BB_FILL)
    }
}

// ------------------------------------------------------------------ tooltip

@Composable
private fun TooltipCard(o:Double,h:Double,l:Double,cl:Double,vol:Long,modifier:Modifier=Modifier){
    val oStr="%.2f".format(o); val hStr="%.2f".format(h)
    val lStr="%.2f".format(l); val cStr="%.2f".format(cl)
    Card(colors=CardDefaults.cardColors(containerColor=Color(0xE6121821)),
         shape=MaterialTheme.shapes.small, modifier=modifier){
        Column(Modifier.padding(8.dp)){
            Text("O $oStr  H $hStr",style=MaterialTheme.typography.labelSmall,color=BULL)
            Text("L $lStr  C $cStr",style=MaterialTheme.typography.labelSmall,color=BEAR)
            Text("V $vol",style=MaterialTheme.typography.labelSmall,color=AXIS_C)
        }
    }
}

// ------------------------------------------------------------------ RSI

@Composable
private fun RsiPanel(values:List<Double?>,candles:List<Candle>,modifier:Modifier=Modifier){
    Box(modifier.background(Color(0xFF0D1117))){
        Canvas(Modifier.fillMaxSize()){
            val w=size.width; val h=size.height
            listOf(30f,70f).forEach{pct->
                val y=h*(1f-pct/100f)
                drawLine(GRID,Offset(0f,y),Offset(w,y),1f)
            }
            val path=Path();var started=false
            val step=w/max(candles.size,1)
            candles.forEachIndexed{i,_->
                values.getOrNull(i)?.let{v->
                    val x=step*i+step/2;val y=h*(1f-v.toFloat()/100f)
                    if(!started){path.moveTo(x,y);started=true}else path.lineTo(x,y)
                }?:run{started=false}
            }
            drawPath(path,LINE_COLOR,style=Stroke(2f))
        }
        Column(Modifier.padding(start=8.dp,top=4.dp)){
            Text("RSI 14",style=MaterialTheme.typography.labelSmall,color=CROSS)
            Text("70 ───",style=MaterialTheme.typography.labelSmall,color=AXIS_C)
        }
    }
}

@Composable private fun AxisText(value:String,modifier:Modifier=Modifier){
    Text(value,style=MaterialTheme.typography.labelSmall,color=AXIS_C,modifier=modifier)
}

object ChartColors{
    val SMA20=SMA20_C;val EMA9=EMA9_C;val BB=LINE_COLOR;val SMA50=Color(0xFFAB47BC)
}

