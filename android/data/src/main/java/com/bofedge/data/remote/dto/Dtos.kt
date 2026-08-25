package com.bofedge.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class FirebaseAuthRequestDto(
    @SerialName("id_token") val idToken: String,
)

@Serializable
data class UserDto(
    @SerialName("id") val id: String,
    @SerialName("firebase_uid") val firebaseUid: String? = null,
    @SerialName("email") val email: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("photo_url") val photoUrl: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("auth_provider") val authProvider: String = "PASSWORD",
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class ApiErrorDto(
    @SerialName("code") val code: String = "UNKNOWN",
    @SerialName("message") val message: String = "Unexpected error",
)
