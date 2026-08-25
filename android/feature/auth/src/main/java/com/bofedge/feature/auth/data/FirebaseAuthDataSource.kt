package com.bofedge.feature.auth.data

import android.content.Context
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.bofedge.domain.error.AuthError
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import com.google.firebase.FirebaseNetworkException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthInvalidCredentialsException
import com.google.firebase.auth.FirebaseAuthInvalidUserException
import com.google.firebase.auth.FirebaseAuthUserCollisionException
import com.google.firebase.auth.FirebaseUser
import com.google.firebase.auth.GoogleAuthProvider
import java.io.IOException
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.tasks.await

/**
 * Thin wrapper over Google Sign-In (Credential Manager) + Firebase Auth.
 *
 * Contract (spec §7):
 *   launch Google Sign-In → credential → Firebase credential → Firebase user
 *   → fresh Firebase ID token for the backend.
 *
 * All SDK exceptions are converted to typed [AuthError]s; cancellation is
 * always rethrown so coroutine scopes stay healthy. The app must never crash
 * because authentication failed.
 */
@Singleton
class FirebaseAuthDataSource @Inject constructor(
    @Named("firebaseWebClientId") private val webClientId: String,
    private val firebaseAuth: FirebaseAuth?,
) {

    /**
     * Runs the Google account picker and returns a verified Google ID token
     * string, or throws a typed [AuthError].
     */
    suspend fun obtainGoogleIdToken(activityContext: Context): String {
        if (webClientId.isBlank()) {
            throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.CONFIGURATION)
        }
        val credentialManager = CredentialManager.create(activityContext)

        val googleIdOption = GetGoogleIdOption.Builder()
            .setServerClientId(webClientId)
            .setFilterByAuthorizedAccounts(false) // show every eligible account
            .setAutoSelectEnabled(false)
            .build()

        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdOption)
            .build()

        val response = try {
            credentialManager.getCredential(activityContext, request)
        } catch (e: GetCredentialCancellationException) {
            throw AuthError.Cancelled
        } catch (e: NoCredentialException) {
            throw AuthError.NoGoogleAccount
        } catch (e: IOException) {
            throw AuthError.GoogleUnavailable
        } catch (e: GetCredentialException) {
            throw AuthError.GoogleUnavailable
        } catch (e: CancellationException) {
            throw e
        }

        val credential = response.credential
        if (credential is CustomCredential &&
            credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
        ) {
            return try {
                GoogleIdTokenCredential.createFrom(credential.data).idToken
            } catch (e: GoogleIdTokenParsingException) {
                throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.INVALID_CREDENTIAL)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                throw AuthError.Unknown(e)
            }
        }
        throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.INVALID_CREDENTIAL)
    }

    /** Signs the Google credential into Firebase; returns the Firebase user. */
    suspend fun signInWithFirebase(googleIdToken: String): FirebaseUser {
        val auth = firebaseAuth
            ?: throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.CONFIGURATION)

        val firebaseCredential = GoogleAuthProvider.getCredential(googleIdToken, null)
        return try {
            auth.signInWithCredential(firebaseCredential).await().user
                ?: throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.OTHER)
        } catch (e: FirebaseAuthInvalidCredentialsException) {
            throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.INVALID_CREDENTIAL)
        } catch (e: FirebaseAuthInvalidUserException) {
            throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.SESSION_EXPIRED)
        } catch (e: FirebaseAuthUserCollisionException) {
            throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.OTHER)
        } catch (e: FirebaseNetworkException) {
            throw AuthError.GoogleUnavailable
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val msg = e.message ?: ""
            if (msg.contains("no longer valid", ignoreCase = true) ||
                msg.contains("expired", ignoreCase = true)
            ) {
                throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.SESSION_EXPIRED)
            }
            throw AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.OTHER)
        }
    }

    /** Fresh Firebase ID token (`getIdToken(false)` lets the SDK refresh). */
    suspend fun idToken(): String? =
        firebaseAuth?.currentUser?.getIdToken(false)?.await()?.token

    fun currentUser(): FirebaseUser? = firebaseAuth?.currentUser

    /** Signs out of Firebase and clears Credential Manager state. */
    suspend fun signOut(context: Context) {
        firebaseAuth?.signOut()
        runCatching {
            CredentialManager.create(context).clearCredentialState(ClearCredentialStateRequest())
        }
    }
}
