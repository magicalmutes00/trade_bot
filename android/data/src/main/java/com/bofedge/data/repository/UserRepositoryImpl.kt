package com.bofedge.data.repository

import com.bofedge.data.remote.BofApi
import com.bofedge.domain.model.AuthUser
import com.bofedge.domain.repository.UserRepository
import com.bofedge.domain.result.ApiResult
import java.io.IOException
import javax.inject.Inject

class UserRepositoryImpl @Inject constructor(
    private val api: BofApi,
) : UserRepository {

    override suspend fun getProfile(): ApiResult<AuthUser> = try {
        val response = api.getProfile()
        val body = response.data
        if (response.success && body != null) {
            ApiResult.Success(body.toDomain())
        } else {
            ApiResult.HttpError(
                code = response.error?.code ?: "UNKNOWN",
                message = response.error?.message ?: "Unexpected server response",
            )
        }
    } catch (e: IOException) {
        ApiResult.Offline
    } catch (e: retrofit2.HttpException) {
        ApiResult.HttpError(code = "HTTP_${e.code()}", message = e.message(), httpStatus = e.code())
    }

    private fun com.bofedge.data.remote.dto.UserDto.toDomain() = AuthUser(
        id = id,
        firebaseUid = firebaseUid,
        email = email,
        displayName = displayName,
        photoUrl = photoUrl ?: avatarUrl,
        authProvider = authProvider,
        isActive = isActive,
    )
}
