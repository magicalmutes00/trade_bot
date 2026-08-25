import { useState } from 'react'
import { login, syncFirebaseUser, fetchProfile } from '../api'
import { googleSignIn } from '../lib/firebase'

function GoogleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47a5.57 5.57 0 0 1-2.4 3.58v3h3.86c2.26-2.09 3.56-5.17 3.56-8.82z" />
      <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09C3.26 21.3 7.31 24 12 24z" />
      <path fill="#FBBC05" d="M5.27 14.29A7.2 7.2 0 0 1 4.89 12c0-.8.14-1.57.38-2.29V6.62H1.29A11.86 11.86 0 0 0 0 12c0 1.94.47 3.76 1.29 5.38l3.98-3.09z" />
      <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.98 3.09C6.22 6.86 8.87 4.75 12 4.75z" />
    </svg>
  )
}

export default function LoginPage({
  onSuccess,
  gateError,
}: {
  onSuccess: (token: string) => void
  gateError?: string | null
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'password' | 'google' | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy('password')
    setError(null)
    try {
      const result = await login(email, password)
      if (result.user.role !== 'ADMIN') {
        throw new Error('This account does not have administrator privileges.')
      }
      onSuccess(result.access_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleGoogle() {
    setBusy('google')
    setError(null)
    try {
      const user = await googleSignIn()          // Firebase popup sign-in
      const idToken = await user.getIdToken()
      await syncFirebaseUser(idToken)            // backend verifies + syncs
      const profile = await fetchProfile(idToken)
      if (profile.role !== 'ADMIN') {
        throw new Error(
          'Signed in, but this account is not an administrator.',
        )
      }
      onSuccess(idToken)                         // live Firebase token as bearer
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Google sign-in failed'
      setError(msg.includes('auth/popup-closed') || msg.includes('popup')
        ? 'Google Sign-In was cancelled.'
        : msg)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-bof-border bg-bof-surface p-8"
      >
        <h1 className="text-xl font-semibold">
          BOF Edge <span className="text-bof-accent">Admin</span>
        </h1>
        <p className="mb-6 mt-1 text-xs text-bof-muted">Administrator sign-in</p>

        {gateError && (
          <div className="mb-4 rounded-md bg-bof-red/10 px-3 py-2 text-xs text-bof-red">{gateError}</div>
        )}
        {error && (
          <div className="mb-4 rounded-md bg-bof-red/10 px-3 py-2 text-xs text-bof-red">{error}</div>
        )}

        {/* Google button first — preferred flow */}
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void handleGoogle()}
          className="flex w-full items-center justify-center gap-3 rounded-md bg-white py-2.5 text-sm font-medium text-[#1F1F1F] transition hover:opacity-90 disabled:opacity-50"
        >
          <GoogleIcon />
          {busy === 'google' ? 'Connecting…' : 'Sign in with Google'}
        </button>

        <div className="my-5 flex items-center gap-3 text-[10px] uppercase tracking-widest text-bof-muted">
          <span className="h-px flex-1 bg-bof-border" />
          or email
          <span className="h-px flex-1 bg-bof-border" />
        </div>

        <label className="mb-1 block text-xs text-bof-muted" htmlFor="email">Email</label>
        <input
          id="email" type="email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-4 w-full rounded-md border border-bof-border bg-bof-black px-3 py-2 text-sm outline-none focus:border-bof-accent"
        />
        <label className="mb-1 block text-xs text-bof-muted" htmlFor="password">Password</label>
        <input
          id="password" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border border-bof-border bg-bof-black px-3 py-2 text-sm outline-none focus:border-bof-accent"
        />

        <button
          type="submit"
          disabled={busy !== null}
          className="mt-5 w-full rounded-md bg-bof-accent py-2 text-sm font-medium text-bof-black transition hover:opacity-90 disabled:opacity-50"
        >
          {busy === 'password' ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
