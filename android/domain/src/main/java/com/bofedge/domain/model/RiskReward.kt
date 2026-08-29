package com.bofedge.domain.model

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Risk/Reward calculation result. */
data class RiskRewardResult(
    val entry: Double,
    val stopLoss: Double,
    val target: Double,
    val risk: Double,
    val reward: Double,
    val riskRewardRatio: Double,  // e.g., 2.0 means 1:2
    val configured: Boolean,
)

/** Configuration for risk/reward calculation. */
data class RiskRewardConfig(
    val allowNegativeRisk: Boolean = false,
    val minRiskRewardRatio: Double = 1.0,  // minimum acceptable R:R ratio
    val roundTo: Int = 2,  // decimal places for display
)

/** Engine for calculating risk/reward ratios.
 *  Inputs: entry, stopLoss, target
 *  Outputs: risk, reward, riskRewardRatio
 */
object RiskRewardEngine {

    /** Calculate risk/reward ratio from entry, stop loss, and target.
     *  Risk = |entry - stopLoss|
     *  Reward = |target - entry|
     *  R:R = reward / risk (if risk > 0)
     */
    fun calculate(entry: Double, stopLoss: Double, target: Double, config: RiskRewardConfig = RiskRewardConfig()): RiskRewardResult {

        val risk = abs(entry - stopLoss)
        val reward = abs(target - entry)

        // Validate: risk must be positive unless configured otherwise
        val riskIsValid = risk > 0 || config.allowNegativeRisk
        val rewardIsValid = reward >= 0

        val riskRewardRatio = if (risk > 0 && riskIsValid) reward / risk else 0.0

        // Check minimum R:R ratio
        val meetsMinRatio = riskRewardRatio >= config.minRiskRewardRatio

        return RiskRewardResult(
            entry = entry,
            stopLoss = stopLoss,
            target = target,
            risk = risk,
            reward = reward,
            riskRewardRatio = riskRewardRatio,
            configured = true,
        )
    }

    /** Format the R:R ratio as a string for display.
     *  Returns formats like "1:2", "1:1", "1:3"
     */
    fun formatRatio(ratio: Double): String {
        val rounded = ratio.roundToInt()
        return "$rounded:$rounded".takeIf { it != "1:1" } ?: "1:1"
    }

    /** Format the R:R ratio with decimal precision.
     *  Returns formats like "1:2.5", "1:1.5"
     */
    fun formatRatioDecimal(ratio: Double, places: Int = 2): String {
        val formatted = String.format("%.${places}f", ratio)
        return formatted
    }
}