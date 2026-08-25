/** Admin API client — Firebase ID token (preferred) or legacy JWT in localStorage. */

import { currentIdToken } from './lib/firebase'

const TOKEN_KEY = 'bof_admin_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function bearer(): Promise<string | null> {
  // Prefer the live Firebase session (auto-refreshes hourly); fall back to a
  // stored legacy email/password JWT so that login path keeps working.
  const fb = await currentIdToken()
  if (fb) return fb
  return getToken()
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await bearer()
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.body ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  const res = await fetch(path, { ...init, headers })

  const body = await res.json().catch(() => null)
  if (!res.ok || body?.success === false) {
    if (res.status === 401) clearToken()
    throw new Error(body?.error?.message ?? `HTTP ${res.status}`)
  }
  return body.data as T
}

// ------------------------------------------------------------------- auth

export interface LoginResult {
  access_token: string
  user: { role: string; email: string; is_active: boolean }
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const body = await res.json()
  if (!res.ok || body.success === false) {
    throw new Error(body.error?.message ?? 'Login failed')
  }
  return {
    access_token: body.data.tokens.access_token,
    user: body.data.user,
  }
}

export async function fetchProfile(tokenOverride?: string): Promise<{ email: string; role: string }> {
  const token = tokenOverride ?? (await currentIdToken()) ?? getToken()
  const res = await fetch('/api/v1/profile', {
    headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  const body = await res.json()
  if (!res.ok || body.success === false) throw new Error(body?.error?.message ?? 'Not authenticated')
  return body.data
}

/** Exchanges a Firebase ID token for the synced application user. */
export async function syncFirebaseUser(idToken: string): Promise<void> {
  const res = await fetch('/api/v1/auth/firebase', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: idToken }),
  })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body?.success) {
    throw new Error(body?.error?.message ?? 'Google sign-in sync failed')
  }
}

// ------------------------------------------------------------------- admin

export interface AdminStats {
  total_users: number; active_users: number
  signals_today: number; total_signals: number
  confirmed_signals: number; invalidated_signals: number
  active_instruments: number; database: string
  ws_connections: number; provider: string; environment: string
}

export interface AdminUserRow {
  id: string; email: string; username: string | null
  display_name: string | null; role: string; auth_provider: string
  is_active: boolean; last_login_at: string | null; created_at: string
}

export interface Paginated<T> { items: T[]; total: number; limit: number; offset: number }

export interface CoverageRow {
  id: string; symbol: string; exchange: string; is_active: boolean
  m15_candles: number; last_m15_ts: string | null; quote_updated_at: string | null
}

export interface SignalRow {
  id: string; symbol: string; direction: string; strength: string
  status: string; timeframe: string; confidence: number; detected_at: string
}

export interface SessionRow {
  id: string; session_date: string; market: string; status: string; note: string | null
}

export interface EventRow {
  id: string; level: string; source: string; message: string; created_at: string
}

export interface AdminHealthInfo {
  status: string; database_latency_ms: number | null
  ws_connections: number; provider: string
  live_loop_enabled: boolean; version: string
}

export const api = {
  stats: () => request<AdminStats>('/api/v1/admin/stats'),
  health: () => request<AdminHealthInfo>('/api/v1/admin/health'),

  users: (q: string, limit = 50, offset = 0) =>
    request<Paginated<AdminUserRow>>(
      `/api/v1/admin/users?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`),
  updateUser: (id: string, patch: { is_active?: boolean; role?: string }) =>
    request<AdminUserRow>(`/api/v1/admin/users/${id}`, {
      method: 'PATCH', body: JSON.stringify(patch),
    }),

  coverage: (limit = 100, offset = 0) =>
    request<Paginated<CoverageRow>>(`/api/v1/admin/instruments?limit=${limit}&offset=${offset}`),
  updateInstrument: (id: string, patch: { is_active?: boolean; name?: string }) =>
    request<{ id: string; symbol: string; is_active: boolean }>(
      `/api/v1/admin/instruments/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  signals: (filters: Record<string, string>, limit = 50, offset = 0) => {
    const qs = new URLSearchParams({ ...filters, limit: String(limit), offset: String(offset) })
    return request<Paginated<SignalRow>>(`/api/v1/admin/signals?${qs}`)
  },

  sessions: () => request<SessionRow[]>('/api/v1/admin/market-sessions'),
  upsertSession: (payload: { session_date: string; market: string; status: string; note?: string }) =>
    request<{ created: boolean }>('/api/v1/admin/market-sessions', {
      method: 'POST', body: JSON.stringify(payload),
    }),

  events: (level: string, limit = 100, offset = 0) => {
    const qs = new URLSearchParams({ level, limit: String(limit), offset: String(offset) })
    return request<Paginated<EventRow>>(`/api/v1/admin/events?${qs}`)
  },
}

