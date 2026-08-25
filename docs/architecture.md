# Architecture

BOF Edge is a monorepo: an Android scanner app, a FastAPI backend, a React
admin panel, and shared documentation.

```
┌─────────────────────┐        HTTPS/JSON          ┌──────────────────────┐
│ Android (Kotlin)    │ ─────────────────────────► │ FastAPI backend      │
│ Compose · Hilt      │   Authorization: Bearer    │ SQLAlchemy 2 async   │
│ Credential Manager  │   (Firebase ID token)      │ PostgreSQL           │
└─────────┬───────────┘                            └──────────┬───────────┘
          │                                                     │
          ▼                                                     ▼
   Firebase Auth                                     BOF engine (Phase 3)
   (identity authority)                              candles → signals
```

## Backend layering

Strict dependency direction — inward only:

```
api (FastAPI routers)
 └─► services (business rules)          e.g. AuthService.firebase_sync()
      └─► repositories (queries)        e.g. UserRepository.get_by_firebase_uid()
           └─► models (SQLAlchemy ORM)  one module per domain area
```

Supporting rings:

| Package | Responsibility |
|---|---|
| `app/core` | config (pydantic-settings), security (Argon2/JWT), Firebase Admin, error types + handlers, rate limiter, logging |
| `app/db` | async engine, session factory, declarative `Base` with naming conventions |
| `app/schemas` | pydantic request/response models; generic `ApiResponse[T]` envelope |
| `app/engine` | BOF detection pipeline — pure functions (see bof-engine.md) |
| `app/websocket` | connection hub, `/ws/market`, live demo loop (ticks/bar closes/pushes) |
| `app/workers` | candle normalisation + demo pipeline orchestration |
| `app/services/providers` | `MarketDataProvider` ABC · Demo (deterministic, labelled) · Real REST vendor (rate-limit + retries + timeouts) · `build_provider()` factory via `MARKET_DATA_PROVIDER` |

### Response envelope

Success `{ "success": true, "data": … }`; failure
`{ "success": false, "error": { "code", "message" } }`. All errors flow
through registered exception handlers (`core/errors.py`) so no endpoint ever
leaks stack traces or driver details.

### Authentication

Two authorities, one user row:

1. **Firebase ID token** (Google Sign-In) — verified server-side via Admin SDK;
   UID/email are only ever read from the *verified* token.
2. **Legacy JWT access token** — Argon2 passwords + rotating refresh sessions
   (`user_sessions` stores SHA-256 hashes only).

`CurrentUser` tries legacy decode first (cheap local check), then Firebase
verification; unknown rotated refresh tokens trigger session revocation for
the whole user (theft guard). See api.md and firebase-setup.md.

### Database schema (16 tables)

users · user_sessions · password_reset_tokens · sectors · instruments ·
market_data · candles · signals · signal_events · watchlists ·
watchlist_items · notification_tokens · notification_preferences ·
user_settings · market_sessions · system_events

Conventions: UUID PKs (`sa.Uuid`), timestamps `timestamptz`, enums stored as
VARCHAR + CHECK (`native_enum=False`) so migrations stay simple, FK cascades
explicit, hot paths indexed (`instrument_id`, `timeframe`, `detected_at`,
`user_id`, composite `(status, strength)`). `candles` uses a composite PK
`(instrument_id, timeframe, ts)` and is deliberately shaped like a
time-series table so it can migrate to a TSDB later without changing callers.
`market_data` holds one latest-quote row per instrument — raw ticks are never
persisted.

Redis is intentionally absent; the in-memory rate limiter hides its storage
behind one function so it can be swapped without touching callers.

## Android architecture

Multi-module Gradle, MVVM + Clean Architecture, unidirectional data flow:

```
:app            MainActivity, auth-state-driven root, MainShell (bottom nav)
:navigation     route table
:feature/auth   FirebaseAuthDataSource → AuthRepositoryImpl → AuthViewModel → LoginScreen
:data           Retrofit/OkHttp client, DTOs, FirebaseAuthInterceptor, UserRepositoryImpl, DI modules
:domain         AuthUser, AuthError, ApiResult, repository interfaces (no framework deps)
:core           theme, reusable UI components (EmptyState/ErrorState/LoadingIndicator)
```

- **Auth routing**: root composable switches on `AuthState` — Checking→splash,
  Unauthenticated→login, Authenticated→shell. Logout anywhere flips state and
  the shell disappears automatically; protected screens can't be reached
  manually after logout.
- **Tokens**: managed entirely by the Firebase SDK. `FirebaseAuthInterceptor`
  attaches `getIdToken(false)` results per request; nothing token-shaped is
  persisted by app code.
- **Errors**: SDK exceptions collapse into typed `AuthError`s at the data
  boundary; the ViewModel maps them to human copy. No stack traces reach UI.

## Admin panel

Vite + React + TypeScript + Tailwind scaffold that talks to the same API
(dev proxy on `/api`). Phase 7 adds real sections behind admin-role auth.

## Environments

| | Local | Production (Render) |
|---|---|---|
| DB | docker-compose Postgres or portable install | Render PostgreSQL |
| Secrets | `.env` (gitignored) | dashboard env vars (`sync: false` in render.yaml) |
| Android base URL | `http://10.0.2.2:8000/api/v1/` | HTTPS Render URL |
