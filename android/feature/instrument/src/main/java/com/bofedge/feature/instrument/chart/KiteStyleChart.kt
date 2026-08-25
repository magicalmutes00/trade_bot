package com.bofedge.feature.instrument.chart

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Spacer
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.bofedge.domain.model.Candle
import kotlin.math.max
import kotlin.math.min

private val BULL = Color(0xFF16C784)
private val BEAR = Color(0xFFEA3943)
private val GRID = Color(0xFF1A2230)
private val CROSS = Color(0xFF4E9CFF)
private val AXIS = Color(0xFF8A97A8)
private val LINE_COLOR = Color(0xFF4E9CFF)
private val BB_FILL = Color(0x154E9CFF)
private val SMA20_C = Color(0xFFFF9800)
private val EMA9_C = Color(0xFFE040FB)

/**
 * Kite/Upstox-style candlestick chart:
 *   - Candlestick rendering (green/red bodies + wicks)
 *   - Crosshair on tap â†’ shows OHLC tooltip at selected bar
 *   - Indicator overlays: SMA(20), EMA(9), Bollinger Bands, SMA(50) â€” toggled externally
 *   - RSI sub-panel below main chart when enabled
 *   - Volume bars in bottom band of price zone
 *   - Right-side price axis labels (max / mid / min)
 *
 * Pure Canvas â€” no chart library dependency.
 */
@Composable
fun KiteStyleChart(
    candles: List<Candle>,
    showSma20: Boolean,
    showEma9: Boolean,
    showSma50: Boolean,
    showBb: Boolean,
    showRsi: Boolean,
    modifier: Modifier = Modifier,
    sma20Values: List<Double?>? = null,
    ema9Values: List<Double?>? = null,
    sma50Values: List<Double?>? = null,
    bbUpper: List<Double?>? = null,
    bbLower: List<Double?>? = null,
    rsiValues: List<Double?>? = null,
) {
    if (candles.isEmpty()) return

    val scale = CandleChartMath.priceScale(candles) ?: return

    // Track which candle the user tapped
    var selectedIndex by androidx.compose.runtime.remember {
        androidx.compose.runtime.mutableIntStateOf(-1)
    }

    Column(modifier) {
        // ---- Main price chart ----
        Row(Modifier.fillMaxWidth()) {
            Box(Modifier.weight(1f).height(if (showRsi) 200.dp else 240.dp)) {
                Canvas(
                    Modifier.fillMaxSize().pointerInput(candles.size) {
                        detectTapGestures { offset ->
                            val step = size.width.toFloat() / candles.size
                            selectedIndex = (offset.x / step).toInt()
                                .coerceIn(0, candles.size - 1)
                        }
                    },
                ) {
                    val w = size.width
                    val priceH = if (showRsi) size.height * 0.82f else size.height * 0.84f
                    val volTop = priceH + 8f
                    val volMaxH = size.height - volTop - 4f

                    fun yPrice(p: Double): Float =
                        priceH * CandleChartMath.yFraction(p, scale)

                    // grid
                    scale.gridLines.forEach { level ->
                        val y = yPrice(level)
                        drawLine(GRID, Offset(0f, y), Offset(w, y), 1f)
                    }

                    val step = w / candles.size
                    val bodyW = max(step * 0.62f, 2f)

                    // Bollinger fill
                    if (showBb && bbUpper != null && bbLower != null) {
                        drawBandFill(candles, bbUpper, bbLower, ::yPrice, step)
                    }

                    // volume
                    val vols = CandleChartMath.volumeFractions(candles)
                    candles.forEachIndexed { i, c ->
                        vols.getOrNull(i)?.let { frac ->
                            val h = volMaxH * frac
                            val col = if (c.isBullish) BULL.copy(alpha = 0.35f)
                                      else BEAR.copy(alpha = 0.35f)
                            drawRect(col, Offset(step*i+step/2-bodyW/2, volTop+(volMaxH-h)), Size(bodyW,h))
                        }
                    }

                    // candles
                    candles.forEachIndexed { i, c ->
                        val cx = step*i+step/2
                        val color = if (c.isBullish) BULL else BEAR
                        drawLine(color, Offset(cx,yPrice(c.high)), Offset(cx,yPrice(c.low)), 2f)
                        val top=yPrice(maxOf(c.open,c.close))
                        val bot=yPrice(minOf(c.open,c.close))
                        drawRoundRect(color, Offset(cx-bodyW/2,top),
                            Size(bodyW,(bot-top).coerceAtLeast(2f)), CornerRadius(2f,2f))
                    }

                    // indicator overlays
                    fun drawLineOverlay(values: List<Double?>, color: Color, width_: Float = 2.5f) {
                        val p = Path()
                        var started = false
                        candles.forEachIndexed { i, _ ->
                            values.getOrNull(i)?.let { v ->
                                val x = step*i+step/2; val y = yPrice(v)
                                if (!started){p.moveTo(x,y);started=true} else p.lineTo(x,y)
                            } ?: run { started = false }
                        }
                        drawPath(p, color, style=Stroke(width_, cap=StrokeCap.Round))
                    }

                    if (showBb && bbUpper != null) drawLineOverlay(bbUpper, LINE_COLOR.copy(alpha=.6f), 1.5f)
                    if (showBb && bbLower != null) drawLineOverlay(bbLower, LINE_COLOR.copy(alpha=.6f), 1.5f)
                    if (showSma20 && sma20Values != null) drawLineOverlay(sma20Values, SMA20_C, 2f)
                    if (showEma9 && ema9Values != null) drawLineOverlay(ema9Values, EMA9_C, 2f)
                    if (showSma50 && sma50Values != null) drawLineOverlay(sma50Values, Color(0xFFAB47BC), 2f)

                    // crosshair
                    if (selectedIndex >= 0 && selectedIndex < candles.size) {
                        val c = candles[selectedIndex]
                        val cx = step*selectedIndex+step/2
                        drawLine(CROSS.copy(.7f), Offset(cx,0f), Offset(cx,priceH), 1.5f)
                        val cy = yPrice(c.close)
                        drawLine(CROSS.copy(.5f), Offset(0f,cy), Offset(w,cy), 1f)
                    }
                }

                // OHLC tooltip overlay
                selectedIndex.let { idx ->
                    if (idx >= 0 && idx < candles.size) {
                        val c = candles[idx]
                        TooltipCard(
                            o=c.open, h=c.high, l=c.low, cl=c.close,
                            vol=c.volume, time=c.timeMillis,
                            Modifier.align(Alignment.TopStart).padding(8.dp),
                        )
                    }
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
        if (showRsi && rsiValues != null) {
            RsiPanel(rsiValues, candles, Modifier.fillMaxWidth().height(80.dp))
        }
    }
}

// ------------------------------------------------------------------ layers

private fun DrawScope.drawBandFill(
    candles: List<Candle>, upper: List<Double?>, lower: List<Double?>,
    yPrice: (Double)->Float, step: Float,
) {
    val upPath = Path(); val loPath = Path()
    var uStarted=false; var lStarted=false
    candles.forEachIndexed{i,_->
        val x=step*i+step/2
        upper.getOrNull(i)?.let{v->val y=yPrice(v);if(!uStarted){upPath.moveTo(x,y);uStarted=true}else upPath.lineTo(x,y)}
        lower.getOrNull(i)?.let{v->val y=yPrice(v);if(!lStarted){loPath.moveTo(x,y);lStarted=true}else loPath.lineTo(x,y)}
    }
    if(uStarted&&lStarted){
        // close band: reverse lower path
        for(i in candles.indices.reversed()){
            lower.getOrNull(i)?.let{v->
                loPath.lineTo(step*i+step/2,yPrice(v))
            }
        }
        upPath.close()
        drawPath(upPath,BB_FILL)
    }
}

// ------------------------------------------------------------------ tooltip

@Composable
private fun TooltipCard(o:Double,h:Double,l:Double,cl:Double,vol:Long,time:Long,modifier:Modifier=Modifier){
    val oStr = "%.2f".format(o)
    val hStr = "%.2f".format(h)
    val lStr = "%.2f".format(l)
    val cStr = "%.2f".format(cl)
    Card(colors=CardDefaults.cardColors(containerColor=Color(0xE6121821)),
         shape=MaterialTheme.shapes.small, modifier=modifier){
        Column(Modifier.padding(8.dp)){
            Text("O $oStr  H $hStr",
                 style=MaterialTheme.typography.labelSmall,color=BULL)
            Text("L $lStr  C $cStr",
                 style=MaterialTheme.typography.labelSmall,color=BEAR)
            Text("V $vol",style=MaterialTheme.typography.labelSmall,color=AXIS)
        }
    }
}

@Composable
private fun RsiPanel(values:List<Double?>,candles:List<Candle>,modifier:Modifier=Modifier){
    Box(modifier.background(Color(0xFF0D1117))){
        Canvas(Modifier.fillMaxSize()){
            val w=size.width; val h=size.height
            // 30/70 guide lines
            listOf(30f,70f).forEach{pct->
                val y=h*(1-pct/100)
                drawLine(GRID,Offset(0f,y),Offset(w,y),1f)
            }
            val path=Path();var started=false
            val step=w/max(candles.size,1)
            candles.forEachIndexed{i,_->
                values.getOrNull(i)?.let{v->
                    val x=step*i+step/2;val y=h*(1f-(v.toFloat()/100f))
                    if(!started){path.moveTo(x,y);started=true}else path.lineTo(x,y)
                }?:run{started=false}
            }
            drawPath(path,LINE_COLOR,style=Stroke(2f))
        }
        // labels
        Column(Modifier.padding(start=8.dp,top=4.dp)){
            Text("RSI 14",style=MaterialTheme.typography.labelSmall,color=CROSS)
            Spacer(Modifier.height(2.dp))
            Text("70 â”€â”€â”€",style=MaterialTheme.typography.labelSmall,color=AXIS)
        }
    }
}

@Composable private fun AxisText(value:String,modifier:Modifier=Modifier){
    Text(value,style=MaterialTheme.typography.labelSmall,color=AXIS,modifier=modifier)
}

// named colors referenced from screen toggle chips
object ChartColors{
    val SMA20=SMA20_C;val EMA9=EMA9_C;val BB=LINE_COLOR;val SMA50=Color(0xFFAB47BC)
}


