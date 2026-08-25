package com.bofedge.data.network

import kotlin.math.min
import kotlin.random.Random

/**
 * Exponential backoff with jitter (spec §13): 1s, 2s, 4s … capped at 30s,
 * ±20% jitter so fleets of clients don't reconnect in lockstep.
 */
object ReconnectBackoff {

    const val BASE_MS = 1_000L
    const val MAX_MS = 30_000L
    const val MAX_ATTEMPTS = 6 // beyond this the delay simply stays at MAX_MS

    fun delayMillis(attempt: Int, random: Random = Random.Default): Long {
        val exponent = attempt.coerceIn(0, MAX_ATTEMPTS)
        val base = min(BASE_MS shl exponent, MAX_MS)
        val jitter = (base * 0.2 * (random.nextDouble() * 2 - 1)).toLong()
        return (base + jitter).coerceIn(250L, MAX_MS)
    }
}
