package com.bofedge.data

import com.bofedge.data.network.MarketSocketClient
import com.bofedge.data.network.ReconnectBackoff
import com.bofedge.data.network.WsEvent
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

class ReconnectBackoffTest {

    @Test
    fun `doubles with jitter around the doubling sequence`() {
        // base ±20% jitter
        assertTrue(ReconnectBackoff.delayMillis(0, Random(1)) in 800..1_200)
        assertTrue(ReconnectBackoff.delayMillis(1, Random(1)) in 1_600..2_400)
        assertTrue(ReconnectBackoff.delayMillis(2, Random(42)) in 3_200..4_800)
    }

    @Test
    fun `caps at thirty seconds regardless of attempt count`() {
        repeat(20) { i ->
            assertTrue(ReconnectBackoff.delayMillis(i + 6, Random(i)) <= ReconnectBackoff.MAX_MS)
            assertTrue(ReconnectBackoff.delayMillis(i + 6, Random(i)) >= 250L)
        }
    }
}

class WsPayloadParsingTest {

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    private fun client() = MarketSocketClient(
        OkHttpClient(), json,
        "wss://example.test/ws/market",
    )

    @Test
    fun `quotes envelope extracts data array`() {
        val c = client()
        val array = c.extractDataArray(
            """{"type":"quotes","data":[{"symbol":"TCS","last_price":4321.5,"change_pct":0.4,"direction":"UP","is_demo":true}]}"""
        )
        assertTrue(array.startsWith("[") && array.endsWith("]"))
    }

    @Test
    fun `quote ticks are parsed and emitted`() {
        val c = client()
        val text = """{"type":"quotes","data":[
            {"symbol":"INFY","last_price":1500.25,"change_pct":-0.31,"direction":"DOWN","is_demo":true,"ts":"2026-08-25T00:00:00+00:00"}
        ]}"""
        c.emitQuotesForTest(text)

        val quotes = c.events.replayCache.filterIsInstance<WsEvent.Quotes>()
        assertEquals(1, quotes.size)
        val tick = quotes.single().ticks.single()
        assertEquals("INFY", tick.symbol)
        assertEquals(1500.25, tick.lastPrice, 0.0001)
        assertEquals("DOWN", tick.direction)
    }

    @Test
    fun `malformed payload never throws`() {
        val c = client()
        c.emitQuotesForTest("{not json")
        // no crash, no event
        assertEquals(0, c.events.replayCache.filterIsInstance<WsEvent.Quotes>().size)
    }
}

private fun MarketSocketClient.emitQuotesForTest(text: String) {
    val m = this.javaClass.getDeclaredMethod("emitQuotes", String::class.java)
    m.isAccessible = true
    m.invoke(this, text)
}
