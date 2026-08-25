package com.bofedge.domain.repository

import com.bofedge.domain.model.AuthUser
import com.bofedge.domain.result.ApiResult

/** Reads application user data from protected backend endpoints. */
interface UserRepository {
    /** GET /api/v1/profile — requires a valid bearer token. */
    suspend fun getProfile(): ApiResult<AuthUser>
}
