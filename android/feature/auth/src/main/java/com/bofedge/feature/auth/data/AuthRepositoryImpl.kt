package com.bofedge.feature.auth.data

import android.content.Context
import com.bofedge.data.remote.BofApi
import com.bofedge.data.remote.dto.FirebaseAuthRequestDto
import com.bofedge.data.remote.dto.UserDto
import com.bofedge.domain.error.AuthError
import com.bofedge.domain.model.AuthUser
import com.bofedge.domain.repository.AuthRepository
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.cancellation.CancellationException

/**
 * Orchestrates the full sign-in pipeline and maps every failure to
 * [AuthError]. Raw tokens/credentials never leave this layer except as the
 * Authorization header handled by [com.bofedge.data.network.FirebaseAuthInterceptor].
 */
@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val dataSource: FirebaseAuthDataSource,
    private val api: BofApi,
) : AuthRepository {

    override suspend fun signInWithGoogle(context: Context): Result<AuthUser> = try {
        // 1-2. Google Sign-In via Credential Manager.
        val googleIdToken = dataSource.obtainGoogleIdToken(context)

        // 3-5. Firebase credential → Firebase user.
        dataSource.signInWithFirebase(googleIdToken)

        // 6. Fresh Firebase ID token for backend verification.
        val idToken = dataSource.idToken()
            ?: throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.SESSION_EXPIRED)

        // 7. FastAPI verifies the token and syncs the PostgreSQL user.
        val response = api.syncFirebaseUser(FirebaseAuthRequestDto(idToken))
        val dto = response.data
        if (!response.success || dto == null) {
            throw AuthError.BackendFailure(
                code = response.error?.code,
                message = response.error?.message,
            )
        }
        Result.success(dto.toDomain())
    } catch (e: CancellationException) {
        throw e
    } catch (e: AuthError) {
        Result.failure(e)
    } catch (e: IOException) {
        Result.failure(AuthError.BackendFailure(code = null, message = null))
    } catch (e: Exception) {
        Result.failure(AuthError.Unknown(e))
    }

    override fun currentUserOrNull(): AuthUser? =
        dataSource.currentUser()?.let { firebaseUser ->
            // Provisional identity from Firebase claims; the authoritative
            // PostgreSQL profile is fetched from /profile once in the shell.
            AuthUser(
                id = firebaseUser.uid,
                firebaseUid = firebaseUser.uid,
                email = firebaseUser.email ?: "",
                displayName = firebaseUser.displayName,
                photoUrl = firebaseUser.photoUrl?.toString(),
                authProvider = firebaseUser.providerData
                    .lastOrNull()?.providerId?.substringBefore('.')?.uppercase() ?: "GOOGLE",
                isActive = true,
            )
        }

    override suspend fun freshIdToken(): String? = try {
        dataSource.idToken()
    } catch (_: Exception) {
        null
    }

    override suspend fun signOut(context: Context) = dataSource.signOut(context)

    private fun UserDto.toDomain() = AuthUser(
        id = id,
        firebaseUid = firebaseUid,
        email = email,
        displayName = displayName,
        photoUrl = photoUrl ?: avatarUrl,
        authProvider = authProvider,
        isActive = isActive,
    )
}
