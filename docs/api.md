# API Reference (v1)

Base URL: `/api/v1` · Interactive OpenAPI: `http://localhost:8000/docs`

## Envelope contract

```json
// success
{ "success": true, "data": { ... } }
// failure
{ "success": false, "error": { "code": "MACHINE_CODE", "message": "human readable" } }
```

Common error codes: `VALIDATION_ERROR` (422) · `UNAUTHENTICATED` / `INVALID_TOKEN` /
`INVALID_CREDENTIALS` (401) · `FORBIDDEN` (403) · `NOT_FOUND` (404) · `CONFLICT`
(409) · `RATE_LIMITED` (429) · `FIREBASE_NOT_CONFIGURED` (503).

## Authentication

### Firebase / Google Sign-In

```
POST /auth/firebase        { "id_token": "<Firebase ID token>" }  → UserResponse
```

The token is verified server-side (Firebase Admin SDK); UID/email are read
only from verified claims. First call provisions a user; repeat calls refresh
profile + `last_login_at`. Legacy email/password accounts sharing the same
email are linked automatically.

Subsequent requests: `Authorization: Bearer <firebase id token>` — attached
automatically by the Android `FirebaseAuthInterceptor`.

### Email/password (legacy, retained)

```
POST /auth/register   { email, password, username?, display_name? } → AuthResponse (201)
POST /auth/login      { email, password }                           → AuthResponse
POST /auth/refresh    { refresh_token }                             → TokenResponse   (rotation + theft guard)
POST /auth/logout     { refresh_token }                             → { revoked }
POST /auth/forgot-password    { email }     → always 200 (no account enumeration)
POST /auth/reset-password     { token, new_password }
```

`AuthResponse = { user: UserResponse, tokens: { access_token, refresh_token,
token_type, expires_in } }`. Access tokens live 30 min; refresh tokens 14 days
and rotate on every use.

Rate limiting: auth endpoints accept ≤10 requests/min/IP (`RATE_LIMITED` on excess).

## User-scoped (bearer required)

```
GET  /profile                 → UserResponse
PATCH /profile                { display_name?, avatar_url? } → UserResponse
GET  /settings                → UserSettingsResponse  (defaults provisioned)
PATCH /settings               { theme?, default_timeframe?, preferences? } → merged
```

## Health

```
GET /healthz                  liveness (no DB)
GET /api/v1/health            readiness incl. database status
```

## Market data (public — Phase 2)

```
GET /dashboard
    → { market_status: {market, status, as_of},
        indices: [QuoteCard…],            // empty until Phase 3 provider
        bof_summary: {active_total, bullish, bearish, strong, new_today, detected_today},
        latest_signals: [SignalCard…], strongest_signals: [SignalCard…] }

GET /instruments?q=&type=&sector_id=&exchange=&sort=&limit=≤100&offset=
    sort ∈ symbol | name | change_pct | volume      (signal sorts arrive in Phase 3)
    → { items: [InstrumentListItem…], total, limit, offset }

GET /instruments/{id}       → InstrumentDetail (quote=null until Phase 3; stats always real)
GET /instruments/{id}/candles?timeframe=1m|5m|15m|30m|1h|4h|1D|1W&limit=≤1000&before=
    → { items: [Candle…], timeframe, limit, has_more }
```

`GET /instruments` and `/dashboard` require no auth (reference/market data);
user-scoped endpoints above always do. Seeded reference data: 50 NSE/BSE
instruments across 13 sectors (`python -m app.cli seed-instruments`, idempotent).

## Signals (public — Phase 3, demo data)

```
GET /signals?instrument_id=&direction=&status=&strength=&min_confidence=
            &timeframe=&detected_from=&detected_to=&sort=detected_at|confidence
            &limit=≤100&offset=
    → { items: [SignalResponse…], total, limit, offset }

GET /signals/{id}                 → SignalDetail (+ lifecycle `events`, `metadata`)
GET /instruments/{id}/signals     → PaginatedSignals (history for one instrument)
```

`SignalResponse` = id, instrument_id, symbol, instrument_name, timeframe,
direction (BULLISH|BEARISH), strength (WEAK→VERY_STRONG), status
(DETECTING|CONFIRMED|INVALIDATED|CLOSED), bof_level, breakout/failure/entry/
stop_reference prices, confidence (0–1), detected_at, confirmed_at.

Engine semantics live in [`bof-engine.md`](bof-engine.md). Demo pipeline:
`python -m app.cli backfill-demo --days 45 [--symbols TCS,INFY]` (idempotent).

## Realtime WebSocket (Phase 4)

```
ws(s)://<host>/ws/market
```

Server pushes JSON envelopes `{"type": "...", "data": {...}}`:

| type | data | cadence |
|---|---|---|
| `hello` | server_time, tick_interval_seconds, provider, is_demo | on connect |
| `quotes` | [{symbol, last_price, change_pct, direction, is_demo, ts}] ×50 | every DEMO_TICK_SECONDS (default 10 s) |
| `signals` | newest CONFIRMED BOF cards (dashboard SignalCard shape) | when a bar close produces them |
| `market_status` | {market, status, as_of} | on session flips |
| `pong` | – | reply to literal text `ping` |

Dead sockets are pruned on first failed broadcast. Demo ticks interpolate the
same deterministic path as stored candles (`is_demo: true` always set).
Android consumes this via `MarketSocketClient` with exponential-backoff
reconnection (1 s → 30 s ±20 % jitter).

## Planned routes (registered per phase)

| Phase | Routes |
|---|---|
| 5 | watchlists CRUD + items, `GET /heatmap` |
| 6 | notification tokens & preferences |

## Conventions

- All timestamps are UTC ISO-8601.
- IDs are UUIDs (strings).
- Errors never expose stack traces, driver details, or token material.
- Every response carries an `x-request-id` header echoed in server logs.
