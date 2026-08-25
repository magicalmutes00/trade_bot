package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Backend response envelope:
 *   { "success": true, "data": ... }  |  { "success": false, "error": {...} }
 */
@Serializable
data class ApiResponseDto<T>(
    @SerialName("success") val success: Boolean = true,
    @SerialName("data") val data: T? = null,
    @SerialName("error") val error: ApiErrorDto? = null,
)
