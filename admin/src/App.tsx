import { useCallback, useEffect, useState } from 'react'
import { clearToken, getToken, setToken, fetchProfile } from './api'
import { watchAuth, firebaseSignOut } from './lib/firebase'
import DashboardPage from './pages/Dashboard'
import UsersPage from './pages/Users'
import InstrumentsPage from './pages/Instruments'
import SignalsPage from './pages/Signals'
import MarketDataPage from './pages/MarketData'
import SessionsPage from './pages/Sessions'
import HealthPage from './pages/Health'
import LogsPage from './pages/Logs'
import LoginPage from './pages/Login'

type PageKey =
  | 'dashboard' | 'users' | 'instruments' | 'signals'
  | 'marketdata' | 'sessions' | 'health' | 'logs'

const NAV: { key: PageKey; label: string }[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'users', label: 'Users' },
  { key: 'instruments', label: 'Instruments' },
  { key: 'signals', label: 'Signals' },
  { key: 'marketdata', label: 'Market Data' },
  { key: 'sessions', label: 'Market Sessions' },
  { key: 'health', label: 'System Health' },
  { key: 'logs', label: 'Logs' },
]

export default function App() {
  const [authed, setAuthed] = useState(false)
  const [checking, setChecking] = useState(Boolean(getToken()))
  const [role, setRole] = useState('')
  const [page, setPage] = useState<PageKey>('dashboard')
  const [gateError, setGateError] = useState<string | null>(null)

  /** Verify the active bearer belongs to an ADMIN; flips the auth gate. */
  const verify = useCallback(async (): Promise<boolean> => {
    try {
      const profile = await fetchProfile()
      if (profile.role !== 'ADMIN') {
        setGateError('This account does not have administrator privileges.')
        setAuthed(false)
        return false
      }
      setRole(profile.role)
      setAuthed(true)
      setGateError(null)
      return true
    } catch {
      setGateError(null)
      setAuthed(false)
      return false
    }
  }, [])

  // Firebase session changes (Google sign-in/out) drive the auth gate.
  useEffect(() => {
    const unsub = watchAuth(async (user) => {
      if (!user) return
      setChecking(true)
      const ok = await verify()
      if (ok) setToken(await user.getIdToken())
      setChecking(false)
    })
    return () => unsub()
  }, [])

  // Legacy email/password session restore (stored JWT).
  useEffect(() => {
    if (!getToken()) {
      setChecking(false)
      return
    }
    void verify().then(() => setChecking(false))
  }, [verify])

  async function handleSignOut() {
    await firebaseSignOut()
    clearToken()
    setAuthed(false)
    setRole('')
  }

  function handleLoginSuccess(token: string) {
    setToken(token)
    void verify()
  }

  if (checking && !authed) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-bof-muted">
        Checking session…
      </div>
    )
  }

  if (!authed) {
    return (
      <LoginPage
        gateError={gateError}
        onSuccess={handleLoginSuccess}
      />
    )
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-bof-border bg-bof-surface">
        <div className="border-b border-bof-border px-5 py-4">
          <div className="font-semibold">BOF Edge <span className="text-bof-accent">Admin</span></div>
          {role && (
            <div className="mt-0.5 text-[10px] uppercase tracking-wider text-bof-muted">{role}</div>
          )}
        </div>
        <nav className="p-3">
          {NAV.map((n) => (
            <button
              key={n.key}
              onClick={() => setPage(n.key)}
              className={`mb-1 w-full rounded-md px-3 py-2 text-left text-sm transition ${
                page === n.key
                  ? 'bg-bof-high font-medium text-bof-accent'
                  : 'text-bof-muted hover:bg-bof-high hover:text-bof-text'
              }`}
            >
              {n.label}
            </button>
          ))}
        </nav>
        <div className="absolute bottom-4 left-3 right-3">
          <button
            onClick={() => void handleSignOut()}
            className="w-full rounded-md border border-bof-border px-3 py-2 text-xs text-bof-muted hover:border-bof-red hover:text-bof-red"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-6">
        {page === 'dashboard' && <DashboardPage />}
        {page === 'users' && <UsersPage />}
        {page === 'instruments' && <InstrumentsPage />}
        {page === 'signals' && <SignalsPage />}
        {page === 'marketdata' && <MarketDataPage />}
        {page === 'sessions' && <SessionsPage />}
        {page === 'health' && <HealthPage />}
        {page === 'logs' && <LogsPage />}
      </main>
    </div>
  )
}
