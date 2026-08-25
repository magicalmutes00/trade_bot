# BOF Edge

A free, production-grade market scanner for breakout-failure (BOF) style
signals. Original implementation and branding — no proprietary code or assets.

> Status: Phase 1 (foundation + authentication) and Google Sign-In are
> implemented and verified. Market-data ingestion (demo provider), the BOF
> engine, WebSocket streaming, heatmap, watchlists and notifications follow in
> later phases — see *Roadmap* below.

```
/bof-scanner
├── android/     Kotlin · Compose · Material3 · Hilt · Retrofit (multi-module)
├── backend/     FastAPI · SQLAlchemy 2 async · Alembic · PostgreSQL
├── admin/       React + TypeScript + Vite + Tailwind (Phase 7)
├── docs/        architecture, api, bof-engine, deployment, firebase-setup
└── docker-compose.yml   (local PostgreSQL)
```

## Authentication

Firebase Authentication is the authority; Google is the provider.

1. Android: Credential Manager → Google → `FirebaseAuth.signInWithCredential`
2. Android obtains the Firebase ID token (`getIdToken(false)` — SDK-managed refresh)
3. `POST /api/v1/auth/firebase {id_token}` — FastAPI verifies via Firebase Admin SDK
4. Backend creates/updates the PostgreSQL user (`firebase_uid` unique,
   legacy email accounts are linked by verified email)
5. All subsequent calls send `Authorization: Bearer <firebase id token>`
   (attached automatically by `FirebaseAuthInterceptor`; never logged)

Legacy email/password auth (Argon2 + rotating refresh sessions) still works
side by side. Details: [`docs/firebase-setup.md`](docs/firebase-setup.md).

## Local setup

### 1. Database

```bash
docker compose up -d          # postgres:16 on :5432 (bof / bof_dev_password)
```

### 2. Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows; source on unix
pip install -r requirements.txt
copy .env.example .env                             # then edit values
alembic upgrade head
uvicorn app.main:app --reload                      # http://localhost:8000/docs
```

Tests: `.venv\Scripts\python -m pytest` (30 tests; run against an isolated
in-memory DB, no services needed. Set `TEST_DATABASE_URL` to exercise Postgres.)

Seed an admin: `python -m app.cli seed-admin --email you@example.com --password ...`

### 3. Android

Open `/android` in Android Studio (or use `gradlew.bat`). Requires
`google-services.json` at `android/app/` and the Web client ID in
`gradle.properties` for sign-in to function — full instructions:
[`docs/firebase-setup.md`](docs/firebase-setup.md).

Debug builds call the backend at `http://10.0.2.2:8000/api/v1/`
(emulator → host loopback). The base URL lives in
`android/data/build.gradle.kts`.

App name is configured once in `android/gradle.properties` (`BOF_APP_NAME`).

### Environment variables (backend)

See `backend/.env.example`. Secrets never go into git:
`DATABASE_URL`, `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`REFRESH_TOKEN_EXPIRE_DAYS`, `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`,
`FIREBASE_PRIVATE_KEY`, `MARKET_DATA_API_KEY`.

## API

Interactive docs: `http://localhost:8000/docs` (OpenAPI). Current endpoints:

| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/auth/register` | – |
| POST | `/api/v1/auth/login` | – |
| POST | `/api/v1/auth/refresh` | – |
| POST | `/api/v1/auth/logout` | – |
| POST | `/api/v1/auth/forgot-password` / `reset-password` | – |
| POST | `/api/v1/auth/firebase` | Firebase ID token |
| GET/PATCH | `/api/v1/profile` | bearer (Firebase or legacy JWT) |
| GET/PATCH | `/api/v1/settings` | bearer |
| GET | `/api/v1/health`, `/healthz` | – |

Envelope contract: success `{ "success": true, "data": … }`,
error `{ "success": false, "error": { "code", "message" } }`.

## Roadmap

Phases 2–9 per project plan: dashboard/instruments/scanner → demo market data +
BOF engine → WebSocket streaming → heatmap/watchlists/signal history → FCM
notifications → admin panel → live provider abstraction → hardening/deploy.
