# Auth

**Tracks:** frontend/src/firebase/config.ts frontend/src/contexts/AuthContext.tsx frontend/src/components/auth/Login.tsx frontend/src/components/layout/ProtectedRoute.tsx backend/services/auth.py backend/services/firms.py backend/routes/websocket_routes.py scripts/bootstrap_firm.py firestore.rules firebase.json

*Last updated: 2026-08-14. See [the knmp journal entry](../journal/entries/2026-08-08-bd-knmp-auth-bypass-fail-closed.md) for the fail-closed bypass work, and [the round-8 entry](../journal/entries/2026-08-13-bd-8bjdx-bug-hunt-round-8.md) for the require_auth route enumeration fix.*

Identity is **Firebase Authentication** (Google + email/password) on the client;
user profiles live in **Firestore**. The Python backend stays stateless — it only
**verifies the Firebase ID token** on the WebSocket handshake via the Firebase Admin
SDK and never holds a session (see
[../standards/stateless-architecture.md](../standards/stateless-architecture.md)).
The only live Firebase project is the demo, `polyglot-demo-aa709` (the former
prod project is dead and unreachable — purge tracked in bd `polyglot-pdf-je6iy`);
the `VFF_DISABLE_AUTH` dev bypass is in
[config-deployment.md](config-deployment.md).

## Frontend (Firebase Auth)

- **Config** — `frontend/src/firebase/config.ts` builds `firebaseConfig` entirely
  from `VITE_FIREBASE_*` env vars (apiKey, authDomain, projectId, …) and exports
  `auth = getAuth(app)` and `db = getFirestore(app)`. **Firestore is the default
  database** — `getFirestore(app)` takes no name. (The old plan assumed a *named* DB
  `polyglotusers`; the code does not use one.)
- **`AuthContext`** (`frontend/src/contexts/AuthContext.tsx`) is the single source of
  client auth state. It provides `user`, `loading`, `signInWithGoogle`,
  `signInWithEmail`, `signUpWithEmail`, `logout`, and `resetPassword`. Persistence is
  `browserLocalPersistence` (`setPersistence`), and `onAuthStateChanged` drives
  `user` / `loading`. **Dev test bypass:** when `isTestHarnessEnabled()`
  (`frontend/src/shared/config.ts` — requires both `__VFF_LOCAL_DEV` and
  `__VFF_TEST_HARNESS`, set via window or localStorage) is true, `AuthContext`
  installs a mock user and skips the Firebase listener entirely (no network, no
  Firestore). This is the client-side companion to the backend `VFF_DISABLE_AUTH`
  bypass and exists only for the E2E voice harness; it can never fire in production
  or normal local dev.
- **Login UI** (`frontend/src/components/auth/Login.tsx`) — a Google button plus an
  email/password form with three modes: `signin`, `signup`, and `reset` (password-
  reset email).
- **Gating** — `frontend/src/components/layout/ProtectedRoute.tsx` renders a spinner
  while `loading`, then renders `<Login />` when `!user`, else the children. It wraps
  the form surface in the schema-forms entry point `frontend/src/schema-forms/main.tsx`
  (`<AuthProvider><ProtectedRoute><SchemaFormDemo/></ProtectedRoute></AuthProvider>`);
  there is no central router/`App.tsx`
  route table. Note `AuthProvider` itself gates on the initial auth check with
  `{!loading && children}`, so anything under the provider (not just `ProtectedRoute`)
  renders **nothing** until that first check resolves — a consumer outside
  `ProtectedRoute` gets no spinner of its own.

### The `authorized_emails` allowlist (email signup only)

`signUpWithEmail` queries the Firestore **`authorized_emails`** collection
(`where('email','==', email.toLowerCase())`) **before** calling
`createUserWithEmailAndPassword`, and throws *"This email is not authorized"* if
there's no match. So email signup is allowlisted; **Google sign-in is not gated by
this check.**

**Firestore rule.** Because that pre-signup query runs while the user is
**unauthenticated**, `firestore.rules` allows an unauthenticated **read** of
`authorized_emails` (and forbids client **writes** — entries are managed out of
band):

```
match /authorized_emails/{doc} {
  allow read: if true;
  allow write: if false;
}
```

> **Deploy note.** The repo `firestore.rules` is the source of truth and is wired
> into `firebase.json` (`firestore.rules`). `deploy-demo.sh` and
> `deploy-production.sh` ship it (`firebase deploy --only firestore:rules`) on any
> frontend/full deploy, so a normal deploy keeps the live rules in sync with the
> repo. A project left on default-deny breaks BOTH email signup (the unauth
> `authorized_emails` read) and the `users/{uid}` profile sync below. Deploy is a
> maintainer action (the NEVER-deploy rule).

## User profile (Firestore `users/{uid}`)

`onAuthStateChanged` syncs a profile doc at **`users/{uid}`** (default DB):

- **First login** — `setDoc` with `{ uid, email, displayName, photoURL, createdAt:
  serverTimestamp(), lastLogin: serverTimestamp(), role: 'user' }`.
- **Return login** — `setDoc({ lastLogin: serverTimestamp() }, { merge: true })`.

(`role` and the `authorized_emails` gate are real and were *not* in the original
plan — verify against code, not the plan.)

**Security rule** (`firestore.rules`) — a user may read/write only their own profile:

```
match /users/{userId} {
  allow read, write: if request.auth != null && request.auth.uid == userId;
}
```

## Backend gate (ID-token verification on `/ws/fill`)

The backend's only auth touchpoint. `backend/services/auth.py` initializes the
Firebase Admin SDK with **ADC** (`firebase_admin.initialize_app()` — Cloud Run
auto-detects credentials; locally needs `gcloud auth application-default login`).
`verify_token(token)` calls `auth.verify_id_token` and returns the decoded claims, or
raises `HTTPException(401)` on failure.

The WebSocket handshake (`backend/routes/websocket_routes.py`):

1. `/ws/fill` takes a **required `token` query param** (`token: str = Query(...)`).
   The frontend appends it to the WS URL — `SchemaForm` calls `user.getIdToken()` and
   threads it through `createConnectionManager` → `WebFormConnection.connect`, which
   does `?token=<idToken>`.
2. `verify_token(token)` runs **before `websocket.accept()`**. On failure the socket
   is closed with **code 1008** ("Authentication failed") and the handler returns —
   no session is created. (The plan mentioned 4001/4003; the code uses 1008.)
3. Only after a valid token does the first-frame handshake proceed (see
   [websocket-routing.md](websocket-routing.md)).

> **Dev bypass.** `VFF_DISABLE_AUTH=true` makes `verify_token` skip verification and
> return a stub `{uid: "dev_user", ...}` (logged `auth_bypassed_via_env`). Local dev
> only, and that is now ENFORCED rather than a convention (bd `polyglot-pdf-knmp`):
> on a deployed service (`K_SERVICE` set by Cloud Run) `Settings` refuses to start,
> and `verify_token` ignores the bypass and falls through to real verification if
> reached anyway. There is no override flag. See
> [config-deployment.md](config-deployment.md).

**HTTP routes (bd polyglot-pdf-z2is).** `require_auth` (also in
`backend/services/auth.py`) is the HTTP counterpart of the WS gate: a FastAPI
dependency reading `Authorization: Bearer <idToken>` and delegating to
`verify_token` (so the same dev bypass applies). It gates FIVE routes: `POST
/api/fill-pdf` (the body carries user-entered field values), the kit-catalogue
reads `GET /api/form-kits` + `GET /api/form-kits/{kit_id}/schema`, and both TTS
routes `POST /api/tts/spellback` + `POST /api/tts/intro` (each synthesizes
audio, so each is paid work as well as a user-data path). The frontend
threads `user.getIdToken()` into those fetches (`pdfFiller.fillPDF`'s optional
`getToken` param; `SchemaFormDemo`'s manifest/schema fetches, where a 401
surfaces as an error instead of silently falling back to the static bundle).
`GET /api/form-kits/{kit_id}/pdf` is **deliberately ungated** — no frontend
consumer loads that route today (the manifest's `pdfPath` is always the static
Hosting path, so the viewer fetches the static copy), and the same
blank-template bytes ship publicly in the frontend bundle regardless; gating it
would protect nothing not already public. The non-gate is pinned by test so a
blanket-auth sweep is a deliberate decision, not an accident.

## Firm identity (`firms/{firm_id}` + custom claims)

The firm tier's identity backbone (bd `polyglot-pdf-lo88`, epic
`polyglot-pdf-02ye`; four-level access model in the
[sprint-19 plan's 2026-08-14 addendum](../sprint_19_firm-tier-kit-lifecycle_plan.md)).

- **Datastore** — Firestore collection **`firms/{firm_id}`** (doc ID =
  operator-chosen slug): `name`, `contact_email`, `allowed_kits: [kit_id]`,
  `status: "active" | "suspended"`, `created_at`/`updated_at`. Accessed ONLY via
  the Admin SDK through `backend/services/firms.py`; `firestore.rules` carries
  an explicit `firms/**` client deny block as defense in depth (the Admin SDK
  bypasses rules, so the block grants nothing — it forecloses any future
  client-SDK path).
- **Read contract — FAIL CLOSED.** `firms.get_allowed_kits(firm_id)` returns
  `[]` on every failure branch (store disabled via `FIRMS_FIRESTORE_ENABLED`,
  missing firm, non-active status, malformed doc, read error) — the deliberate
  inverse of the confirmation sink's fail-open writes, because a broken firms
  store must never widen private-kit visibility (consumer: bd
  `polyglot-pdf-vccy`). `firms_store_status()` is the read-shaped health probe
  for diagnosing exactly that fail-closed silence.
- **Staff identity** — `firm_id` + `firm_role` (`manager` | `employee`) custom
  claims on the staff member's normal Firebase account, stamped by the admin
  bootstrap script below. The claims ride the existing ID-token verification
  (`require_auth` / the WS `?token=` gate); nothing reads them yet — bd
  `polyglot-pdf-vccy` (visibility) and bd `polyglot-pdf-xwlt` (telemetry) are
  the consumers. A stamped claim appears in decoded tokens only on the next
  token refresh (up to ~1h; force via sign-out/in or `getIdToken(true)`).

**The admin step** (creates/updates the firm record and stamps staff claims;
full usage, `--dry-run`, and the exit-code contract live in the script
docstring):

```bash
backend/.venv/Scripts/python.exe scripts/bootstrap_firm.py acme-legal \
    --name "Acme Legal Aid" --contact intake@acme-legal.example \
    --allowed-kits w7,i-90 \
    --manager-email ada@acme-legal.example \
    --employee-email bo@acme-legal.example \
    --project polyglot-demo-aa709
```

Rules for `firms/**` reach the live project only via a frontend/full deploy or
an explicit
`firebase deploy --only firestore:rules --project polyglot-demo-aa709` — a
backend-only deploy does NOT ship rules. Manual verify of the deny: from a
signed-in browser console, a client-SDK `getDoc(doc(db, "firms", "x"))` must
return `permission-denied`.

## Testing

The WS auth gate is covered indirectly: the integration tests patch
`backend.routes.websocket_routes.verify_token`
(`backend/tests/integration/test_websocket_ephemeral.py`) so the handshake tests run
without a live token. The HTTP gate is covered directly:
`backend/tests/unit/test_http_route_auth.py` pins the 401s on
fill-pdf/form-kits/schema, the deliberate NON-gate on the kit-PDF GET, and the
`VFF_DISABLE_AUTH` bypass, and `backend/tests/unit/test_auth_bypass_guard.py`
pins the deployed fail-closed guard on that bypass (both layers separately: the
`Settings` startup refusal and `verify_token`'s inert-on-`K_SERVICE` branch).
The firm-identity layer is covered by
`backend/tests/unit/test_firms_service.py` (fail-closed reads, upsert
idempotency), `backend/tests/unit/test_bootstrap_firm_cli.py` (claims merge,
role stamping, wrong-project abort, dead-project refusal), and
`backend/tests/unit/test_firestore_rules_text.py` (the `firms/**` deny block's
presence in the shipped rules file).
`frontend/src/contexts/AuthContext.test.tsx` covers
`AuthContext` (the authorized_emails allowlist gate, sign-in/out/reset delegation,
the loading lifecycle, and the test-harness bypass) and `ProtectedRoute` (both gate
states). There are no tests yet for `Login` (the form/UI component itself).
See [../standards/testing.md](../standards/testing.md).
