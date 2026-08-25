package com.bofedge.domain.result

/**
 * Uniform result wrapper mirroring the backend contract:
 *   success -> { "success": true, "data": ... }
 *   failure -> { "success": false, "error": { "code", "message" } }
 */
sealed class ApiResult<out T> {
    data class Success<T>(val value: T) : ApiResult<T>()

    /** Server reachable but returned an error envelope / HTTP error. */
    data class HttpError(val code: String, val message: String, val httpStatus: Int? = null) :
        ApiResult<Nothing>()

    /** No connectivity / DNS / timeout. */
    object Offline : ApiResult<Nothing>()
}

inline fun <T, R> ApiResult<T>.map(transform: (T) -> R): ApiResult<R> = when (this) {
    is ApiResult.Success -> ApiResult.Success(transform(value))
    is ApiResult.HttpError -> this
    is ApiResult.Offline -> this
}
