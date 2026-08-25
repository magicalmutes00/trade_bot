# Deployment (Render)

## Services

`render.yaml` at the repo root defines:

- **bof-scanner-db** — Render PostgreSQL (free tier)
- **bof-scanner-api** — FastAPI web service
  - Root dir: `backend`
  - Build: `pip install -r requirements.txt`
  - Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  - Health check: `/healthz`

Deploy: Render Dashboard → **New → Blueprint** → select the repo.
Render injects `DATABASE_URL` from the database automatically.

## Environment variables (set in the Render dashboard)

Configure under *bof-scanner-api → Environment*. Never commit real values —
in `render.yaml` these are declared with `sync: false`, which tells Render to
prompt for them (or reuse existing values) without storing them in the file.

| Variable | Notes |
|---|---|
| `JWT_SECRET` | Long random string (`generateValue: true` on first deploy) |
| `FIREBASE_PROJECT_ID` | e.g. `bofedge-f72ae` |
| `FIREBASE_CLIENT_EMAIL` | Service-account email from Firebase console |
| `FIREBASE_PRIVATE_KEY` | PEM key; literal `\n` sequences are normalized by the backend |
| `MARKET_DATA_API_KEY` | Optional until Phase 8 |
| `CORS_ORIGINS` | Comma-separated origins; admin panel origin goes here |

`DATABASE_URL` is injected by Render — do not set it manually.

## Firebase Admin on Render

The Admin SDK authenticates with the three `FIREBASE_*` variables above via a
constructed service-account certificate (`backend/app/core/firebase.py`). No
JSON key file is stored on disk; the private key lives only in the encrypted
Render environment.

## Android release builds

1. Register the release/Play signing SHA-1 + SHA-256 in Firebase console
   (see docs/firebase-setup.md §1).
2. Point `android/data/build.gradle.kts` release `BOF_BASE_URL` at the Render
   URL (already defaulted to `https://bof-edge-backend.onrender.com/api/v1/`).
3. Ensure HTTPS-only: release builds never use cleartext hosts.
