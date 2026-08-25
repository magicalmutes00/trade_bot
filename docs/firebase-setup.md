# Firebase & Google Sign-In Setup

BOF Edge uses **Firebase Authentication** as the authentication authority.
The Android app signs the user in with Google, obtains a **Firebase ID
token**, and sends it to FastAPI as `Authorization: Bearer <token>`. The
backend verifies the token with the Firebase Admin SDK and syncs a
PostgreSQL user. No Google passwords ever reach our servers.

```
Android → Google Sign-In → Firebase Auth → ID token → FastAPI (Admin SDK verify)
        → create/update PostgreSQL user → app session
```

---

## 1. Create / configure the Firebase project

Current project: **`bofedge-f72ae`** — Android package registered:
**`com.trisentric.bofedge`** (this is why `applicationId` in
`android/app/build.gradle.kts` is set to that value; keep them in sync).

1. Open <https://console.firebase.google.com> and select the project.
2. **Project settings → Your apps → Android app**
   - Package name: `com.trisentric.bofedge` (must equal `applicationId`)
   - App nickname: `BOF Edge`
3. **Add fingerprints** (both are required for Google Sign-In to work):

   Debug keystore (`%USERPROFILE%\.android\debug.keystore`, store password
   `android`) on this machine:

   ```
   SHA-1:   7A:0B:28:45:EF:A3:87:BA:80:88:37:BF:D4:DC:AC:82:07:B8:49:18
   SHA-256: B1:62:34:E5:B9:DC:69:38:FB:61:EF:B8:61:05:C9:B4:BF:54:50:3E:53:B8:B7:2C:59:7C:B4:88:1B:2B:D3:1A
   ```

   Obtain them yourself any time:

   ```powershell
   # From android/ :
   .\gradlew.bat signingReport          # lists debug + release fingerprints

   # or directly with keytool:
   keytool -list -v -alias androiddebugkey `
     -keystore "$env:USERPROFILE\.android\debug.keystore" -storepass android
   ```

   For **release** builds add the fingerprints of your release/Play-App-Signing
   key. Google Sign-In silently fails with `ApiException 10` / "no credential"
   when the fingerprint of the *signing* certificate is missing — debug and
   release certificates each need their own entry.

4. Download **`google-services.json`** from Project settings → Your apps.
5. Place it at exactly:

   ```
   android/app/google-services.json
   ```

   The file is **gitignored** (root `.gitignore` contains
   `google-services.json`). The Gradle google-services plugin is applied only
   when this file exists, so a clean checkout still compiles — but runtime
   Firebase calls will fail until you add it.

## 2. Enable Authentication

1. **Build → Authentication → Get started**.
2. **Sign-in method → Google → Enable**.
3. Set the project **support email** when prompted.
4. Save. Note the **Web client ID** shown under *Web SDK configuration* — you
   will paste it in step 4 below.

## 3. Backend credentials (Firebase Admin SDK)

Create a service account for the backend:

1. **Project settings → Service accounts → Generate new private key**
2. Copy three values into environment variables (**never into code**):

| Variable | Value |
|---|---|
| `FIREBASE_PROJECT_ID` | e.g. `bofedge-f72ae` |
| `FIREBASE_CLIENT_EMAIL` | `firebase-adminsdk-…@bofedge-f72ae.iam.gserviceaccount.com` |
| `FIREBASE_PRIVATE_KEY` | The PEM key — literal `\n` sequences are handled safely by `app/core/firebase.py` |

Local dev: put them in `backend/.env` (gitignored). See `.env.example`.
Render: set the same variables in the dashboard (see `docs/deployment.md`;
`render.yaml` intentionally declares them as `sync: false`).

Without these variables the API returns
`503 {"error":{"code":"FIREBASE_NOT_CONFIGURED"}}` from `/auth/firebase`,
and protected endpoints fall back cleanly to legacy JWT auth.

## 4. Android Web client ID

In `android/gradle.properties`:

```properties
BOF_FIREBASE_WEB_CLIENT_ID=<Web client ID from Authentication → Google → Web SDK configuration>
```

It flows into `BuildConfig.FIREBASE_WEB_CLIENT_ID` and is used by Credential
Manager (`GetGoogleIdOption.setServerClientId`). It is not a secret, but it
is kept out of Kotlin sources per project policy. If it's blank, sign-in
fails with *"Google Sign-In is not configured on this build."*

## 5. How it works at runtime

- Sign-in: Credential Manager account picker → `GoogleIdTokenCredential`
  → `FirebaseAuth.signInWithCredential(GoogleAuthProvider.getCredential(...))`
  → `getIdToken(false)` → `POST /api/v1/auth/firebase {id_token}`.
- Every subsequent API call carries
  `Authorization: Bearer <firebase id token>` via
  `FirebaseAuthInterceptor` (tokens auto-refresh through the Firebase SDK;
  they are never logged or persisted).
- Logout: `FirebaseAuth.signOut()` + Credential Manager state cleared;
  local UI state resets; navigation returns to Login automatically because
  root routing is driven by `AuthState`.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ApiException 10` / no accounts shown | Missing/wrong SHA-1 for the certificate actually signing the APK |
| Works on emulator, not device (or reverse) | Different signatures — register both fingerprints |
| 503 FIREBASE_NOT_CONFIGURED | Backend env vars missing |
| 401 INVALID_TOKEN on `/auth/firebase` | Token expired or from another Firebase project |
