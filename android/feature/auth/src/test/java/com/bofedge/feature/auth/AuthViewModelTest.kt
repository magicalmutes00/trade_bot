package com.bofedge.feature.auth

import android.content.Context
import com.bofedge.domain.error.AuthError
import com.bofedge.domain.model.AuthUser
import com.bofedge.domain.repository.AuthRepository
import com.bofedge.feature.auth.presentation.AuthState
import com.bofedge.feature.auth.presentation.AuthViewModel
import com.bofedge.feature.auth.presentation.userMessage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

private val FAKE_USER = AuthUser(
    id = "11111111-1111-1111-1111-111111111111",
    firebaseUid = "fb-123",
    email = "g.user@gmail.com",
    displayName = "Google User",
    photoUrl = null,
    authProvider = "GOOGLE",
    isActive = true,
)

/** Deterministic in-memory fake â€” no Firebase/Google SDK involvement. */
private class FakeAuthRepository(
    var existingUser: AuthUser? = null,
    var signInResult: Result<AuthUser>? = null,
) : AuthRepository {
    var signOutCalled = false

    override suspend fun signInWithGoogle(context: Context): Result<AuthUser> =
        signInResult ?: throw IllegalStateException("signInResult not configured")

    override fun currentUserOrNull(): AuthUser? = existingUser

    override suspend fun freshIdToken(): String? = "token"

    override suspend fun signOut(context: Context) {
        signOutCalled = true
        existingUser = null
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun viewModel(repo: FakeAuthRepository): AuthViewModel =
        AuthViewModel(repo).also { dispatcher.scheduler.advanceUntilIdle() }

    @Test
    fun `cold start with no firebase session lands on Unauthenticated`() {
        val vm = viewModel(FakeAuthRepository(existingUser = null))
        assertEquals(AuthState.Unauthenticated, vm.state.value)
    }

    @Test
    fun `cold start with an existing firebase session skips login`() {
        val vm = viewModel(FakeAuthRepository(existingUser = FAKE_USER))
        assertEquals(AuthState.Authenticated(FAKE_USER), vm.state.value)
    }

    @Test
    fun `successful google sign-in transitions to Authenticated`() = runTest {
        val repo = FakeAuthRepository(signInResult = Result.success(FAKE_USER))
        val vm = viewModel(repo)

        vm.signInWithGoogle()
        dispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.state.value is AuthState.Authenticated)
    }

    @Test
    fun `user cancellation surfaces a friendly message, never a crash`() = runTest {
        val repo = FakeAuthRepository(signInResult = Result.failure(AuthError.Cancelled))
        val vm = viewModel(repo)

        vm.signInWithGoogle()
        dispatcher.scheduler.advanceUntilIdle()

        val state = vm.state.value
        assertTrue(state is AuthState.Error)
        assertEquals("Google Sign-In was cancelled.", (state as AuthState.Error).message)

        vm.clearError()
        assertEquals(AuthState.Unauthenticated, vm.state.value)
    }

    @Test
    fun `backend failure maps to server copy without leaking internals`() = runTest {
        val repo = FakeAuthRepository(
            signInResult = Result.failure(AuthError.BackendFailure(code = "X", message = null)),
        )
        val vm = viewModel(repo)

        vm.signInWithGoogle()
        dispatcher.scheduler.advanceUntilIdle()

        val state = vm.state.value as AuthState.Error
        assertEquals("Unable to connect to the BOF server. Please try again shortly.", state.message)
    }

    @Test
    fun `logout clears authenticated state`() = runTest {
        val repo = FakeAuthRepository(existingUser = FAKE_USER)
        val vm = viewModel(repo)
        assertEquals(AuthState.Authenticated(FAKE_USER), vm.state.value)

        vm.logout()
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(AuthState.Unauthenticated, vm.state.value)
        assertTrue(repo.signOutCalled)
    }

    @Test
    fun `error copy catalogue matches spec wording`() {
        assertEquals("Your session has expired. Please sign in again.",
            AuthError.FirebaseFailure(AuthError.FirebaseFailure.Reason.SESSION_EXPIRED).userMessage())
        assertEquals("Something went wrong. Please try again.",
            AuthError.Unknown().userMessage())
    }
}

/**
 * A Mockito mock is safe here: the fake repository never invokes methods on
 * the context, it only needs to satisfy the non-null signature.
 */
private val noContext: Context = org.mockito.Mockito.mock(Context::class.java)

private fun AuthViewModel.signInWithGoogle() = signInWithGoogle(noContext)
private fun AuthViewModel.logout() = logout(noContext)

