# BoostX

System monitor, boost, cleaner and game launcher desktop app (PySide6).

```bash
.venv/bin/python -m boostx
```

## Account & Backend

BoostX talks to the [BoostX-Server](../BoostX-Server) backend for account
authentication, subscription status and device management. No UI page performs
HTTP requests directly — everything goes through the service layer in
`boostx/core/services/api/`:

- `ApiClient` — thin `httpx`-based HTTP wrapper.
- `AuthService` — one method per backend endpoint, returns plain dataclasses.
- `SessionManager` — the only thing UI code talks to. Runs all network calls on
  a background thread pool (`api_worker.run_async`) so the UI never blocks, and
  owns the JWT access/refresh token lifecycle (rotation, silent refresh,
  logout).
- `TokenStorage` — persists only the refresh token to disk
  (`data/session.json`, `chmod 600` on POSIX). Passwords and access tokens are
  never written to disk.

Configure the backend URL with the `BOOSTX_API_URL` environment variable
(defaults to `http://localhost:8000/api/v1`):

```bash
export BOOSTX_API_URL=http://localhost:8000/api/v1
.venv/bin/python -m boostx
```

### Startup flow

1. `AppController` asks `SessionManager` to restore a session from the stored
   refresh token.
2. If the backend confirms the token, the session is restored and the
   Dashboard opens directly.
3. If the backend is unreachable but a cached profile exists locally, the app
   opens in **offline mode** (a banner is shown) and keeps retrying every 30s
   until it can silently resync.
4. Otherwise, the Login screen is shown. From there users can register, verify
   their email (6-digit code), or reset a forgotten password.
5. On successful login/verification, the app switches to the main window.
   Logging out (Account page) returns to the Login screen.
