# Auth

**Tracks:** frontend/src/firebase/config.ts frontend/src/contexts/AuthContext.tsx frontend/src/components/auth/Login.tsx frontend/src/components/layout/ProtectedRoute.tsx backend/services/auth.py backend/routes/websocket_routes.py firestore.rules firebase.json

*Last updated: 2026-06-04. See [../journal/entries/2026-06-04-bd-bmz-firestore-authorized-emails-rule.md](../journal/entries/2026-06-04-bd-bmz-firestore-authorized-emails-rule.md) for closeout details.*

Identity is **Firebase Authentication** (Google + email/password) on the client;
user profiles live in **Firestore**. The Python backend stays stateless — it only
**verifies the Firebase ID token** on the WebSocket handshake via the Firebase Admin
SDK and never holds a session (see
[../standards/stateless-architecture.md](../standards/stateless-architecture.md)).
The two Firebase projects (demo `polyglot-demo-aa709`, prod `polyglot-forms-919f2`)
and the `VFF_DISABLE_AUTH` dev bypass are in
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
  `user` / `loading`.
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

> **Deploy note (bd `polyglot-pdf-bmz`).** The repo `firestore.rules` is now the
> intended source of truth and is wired into `firebase.json` (`firestore.rules`),
> but the **deployed** rules can lag until someone runs
> `firebase deploy --only firestore:rules` per project. As of this fix the demo
> project (`polyglot-demo-aa709`) had pure default-deny deployed (no
> `authorized_emails` **and** no `/users` rule), so email signup AND the profile
> sync below were both failing there until the corrected rules are deployed. The
> deploy is a maintainer action.

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
> only — never set in prod. See [config-deployment.md](config-deployment.md).

## Testing

The WS auth gate is covered indirectly: the integration tests patch
`backend.routes.websocket_routes.verify_token`
(`backend/tests/integration/test_websocket_ephemeral.py`) so the handshake tests run
without a live token. There are **no frontend tests** for `AuthContext` / `Login` /
`ProtectedRoute` yet. See [../standards/testing.md](../standards/testing.md).
