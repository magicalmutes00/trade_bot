package com.bofedge.feature.instrument

import com.bofedge.domain.model.RiskRewardResult
import com.bofedge.domain.model.RiskRewardConfig
import org.junit.Assert.assertEquals
import org.junit.Test

class RiskRewardEngineTest {

    @Test
    fun `basic_risk_reward_calculation_1_2_ratio`() {
        // Entry = 1420, Stop = 1380, Target = 1500
        // Risk = 40, Reward = 80, R:R = 1:2
        val result = RiskRewardEngine.calculate(1420.0, 1380.0, 1500.0)

        assertEquals(40.0, result.risk, 0.001)
        assertEquals(80.0, result.reward, 0.001)
        assertEquals(2.0, result.riskRewardRatio, 0.001)
    }

    @Test
    fun `1_1_risk_reward_ratio`() {
        // Entry = 100, Stop = 95, Target = 105
        // Risk = 5, Reward = 5, R:R = 1:1
        val result = RiskRewardEngine.calculate(100.0, 95.0, 105.0)

        assertEquals(5.0, result.risk, 0.001)
        assertEquals(5.0, result.reward, 0.001)
        assertEquals(1.0, result.riskRewardRatio, 0.001)
    }

    @Test
    fun `config_min_risk_reward_ratio`() {
        val config = RiskRewardConfig(minRiskRewardRatio = 2.0)
        val result = RiskRewardEngine.calculate(100.0, 95.0, 110.0, config)

        // Risk = 5, Reward = 10, R:R = 2.0 meets the minimum
        assertEquals(5.0, result.risk, 0.001)
        assertEquals(10.0, result.reward, 0.001)
        assertEquals(2.0, result.riskRewardRatio, 0.001)
    }

    @Test
    fun `allow_negative_risk_config`() {
        // When allowNegativeRisk is true, risk can be 0
        val config = RiskRewardConfig(allowNegativeRisk = true)
        val result = RiskRewardEngine.calculate(100.0, 100.0, 110.0, config)

        assertEquals(0.0, result.risk, 0.001)
        assertEquals(10.0, result.reward, 0.001)
    }

    @Test
    fun `risk_reward_result_fields`() {
        val result = RiskRewardResult(
            entry = 100.0,
            stopLoss = 95.0,
            target = 110.0,
            risk = 5.0,
            reward = 15.0,
            riskRewardRatio = 3.0,
            configured = true,
        )

        assertEquals(100.0, result.entry)
        assertEquals(95.0, result.stopLoss)
        assertEquals(110.0, result.target)
        assertEquals(5.0, result.risk)
        assertEquals(15.0, result.reward)
        assertEquals(3.0, result.riskRewardRatio)
        assertEquals(true, result.configured)
    }
}