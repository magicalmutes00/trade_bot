package com.bofedge.domain.model

/**
 * Application user, built exclusively from server-verified data:
 * Firebase ID-token claims verified by FastAPI, mirrored in PostgreSQL.
 */
data class AuthUser(
    val id: String,
    val firebaseUid: String?,
    val email: String,
    val displayName: String?,
    val photoUrl: String?,
    val authProvider: String,
    val isActive: Boolean,
)
