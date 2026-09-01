# Auth

**Tracks:** frontend/src/firebase/config.ts frontend/src/contexts/AuthContext.tsx frontend/src/components/auth/Login.tsx frontend/src/components/layout/ProtectedRoute.tsx backend/services/auth.py backend/services/firms.py backend/services/kit_gates.py backend/routes/websocket_routes.py scripts/bootstrap_firm.py firestore.rules firebase.json

*Last updated: 2026-08-20. See [the xwlt journal entry](../journal/entries/2026-08-20-bd-xwlt-firm-telemetry.md) for the firm-keyed voice telemetry (the claim's second consumer), [the vccy journal entry](../journal/entries/2026-08-18-bd-vccy-firm-scoped-kit-visibility.md) for firm-scoped kit visibility (the first consumer of the firm claims), [the knmp journal entry](../journal/entries/2026-08-08-bd-knmp-auth-bypass-fail-closed.md) for the fail-closed bypass work, and [the round-8 entry](../journal/entries/2026-08-13-bd-8bjdx-bug-hunt-round-8.md) for the require_auth route enumeration fix.*

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
> into `firebase.json` (`firestore.rules`). `deploy-demo.sh` ships it
> (`firebase deploy --only firestore:rules`) on any
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
`verify_token` (so the same dev bypass applies). It gates `POST
/api/fill-pdf` (the body carries user-entered field values), `POST
/api/tts/notice` (bd `polyglot-pdf-dft1` -- the app's OWN safety notices,
spoken free: the paid dependency would redeem the link, answering a
budget-exhausted client with silence and burning a live client's link to
deliver a warning we chose to give. It speaks only KEYED server-side text, so
being free does not make it an open text-to-speech service), `POST
/api/resume-form` (bd `polyglot-pdf-dft1` -- a client uploads the PDF they
saved earlier; it reads the kit's own form.pdf as the REFERENCE to verify
that upload against, so it carries the same gates as the fill route.
Deliberately NOT `require_paid_client_work`: resuming your own saved work
spends nothing and must not burn the link), the
archived-revision reads `GET /api/form-kits/{kit_id}/archive` +
`.../archive/{marker}/schema` (bd `polyglot-pdf-qfyxr`; same firm-visibility
gates as the live schema read), `POST /api/form-kits/{kit_id}/retire` (bd
`polyglot-pdf-z6bk9` -- the firm tier's only WRITE path; `require_auth` is
necessary but nowhere near sufficient there, see below), `POST
/api/links/mint` (bd `polyglot-pdf-ugm6` -- firm staff mint a CLIENT link; a
client credential is refused here because minting needs a `uid` and a client
has none). The two TTS routes `POST /api/tts/spellback` + `POST
/api/tts/intro` are gated by the STRICTER `require_paid_client_work`
instead: each synthesizes audio, so each is real spend, and a completed
client link must buy no more of it.

**That split is the shape of the client TTL** (maintainer, 2026-08-24: "The
TTL should be backend connection"). Completing a form bounds a new BACKEND
CONNECTION -- a Gemini session, a synthesis call. It does NOT bound the
client downloading, printing or previewing the document they just filled:
`/api/fill-pdf` is a pure PyMuPDF render with no model call, so a clock on it
buys no security and only loses the client their work. Retrieval still
requires a valid signed link inside its open window, scoped to that link's
single kit. The frontend
threads `user.getIdToken()` into those fetches (`pdfFiller.fillPDF`'s optional
`getToken` param; `SchemaFormDemo`'s manifest/schema fetches, where a 401
surfaces as an error instead of silently falling back to the static bundle).
**Selecting a form is NOT gated on enrolment.** The kit-catalogue reads --
`GET /api/form-kits` and `GET /api/form-kits/{kit_id}/schema` -- use
`require_signin` instead: a valid Firebase token is required, a firm or dev
claim is not. Maintainer, 2026-08-25: *"choosing a form to work on is a
fundamental part of using the voice app and the whole app is blocked without
access to that ... anyone using the app must have access to at least one form
kit."* Future users arrive by magic link with no firm claim, so gating the
catalogue leaves them in an app with nothing to pick and no way out -- the
only remedy the UI can offer is "sign in again", which was never the problem.

This costs no confidentiality: both routes already filter to kits that are
PUBLIC or in the caller's own firm allowlist (`_firm_allowed_kits`), and the
schema route 404s a private kit the caller cannot see. Enrolment never
protected a private kit here; it only decided whether someone saw the public
ones. `backend/tests/unit/test_http_route_auth.py` pins BOTH sets -- the
browse routes and the gated routes -- so a route moving between them fails
loudly rather than as "no forms found".

`require_signin` ALSO accepts a client link token, by the same shape dispatch
`require_auth` uses (and likewise without redeeming -- browsing the form you
were sent must not burn the link). It has to: these are the client's first
two calls, so refusing a link here dead-ends the client tier on this surface
alone, with every other door still working. That is not hypothetical -- it is
what the ugm6/#643 merge produced, caught by the credential-site set guard in
`test_client_link_http_auth.py` and now pinned over real HTTP by
`backend/tests/integration/test_client_link_journey.py`.

### Client magic links -- the THIRD credential system

`bd polyglot-pdf-ugm6`. **A firm's CLIENT never signs in.** They are our
customer's customer; they have no account and must never have one (maintainer,
2026-08-17, who also explicitly rejected the alternative of a client working on
a staff-signed-in machine). Their entry is a one-time link.

**Three credential systems now exist, and they must not merge:**

| # | Who | Credential | Where |
|---|-----|-----------|-------|
| 1 | Firm STAFF (voice app) | per-user Firebase ID token + `firm_id`/`firm_role` claims | `services/auth.py` |
| 2 | Schema EDITOR | its own per-user identity (epic `polyglot-pdf-ijntk`) | `services/editor_auth.py` |
| 3 | Firm CLIENT | a signed magic-link token | `services/link_tokens.py` |

They are kept apart STRUCTURALLY, not by convention: a link token has ONE
dot, a Firebase JWT has two, so neither verifier can silently accept the
other's token. `/ws/fill` dispatches on that shape (`_verify_ws_credential`),
so a caller cannot opt into the weaker check by labelling their credential.

**The `jti` reaches our records, or the split key is not a key.** Both
session events (`form_session_started` / `form_session_ended`) carry
`link_jti` and `employee_id`. Without that column the firm holds one half of
a join with nothing on our side to join to, and the arrangement this whole
design exists to provide -- the firm can re-identify, we cannot -- silently
does not work. `employee_id` on the same records is what makes a CLIENT
session satisfy the telemetry requirement (firm + form + originating
employee) despite there being no account anywhere.

**The token carries `{firm_id, kit_id, employee_id, jti, iat, exp, cw}` and
DELIBERATELY no client identifier.** That absence is the product's legal
posture, not privacy hygiene: WE hold a pseudonymous record keyed by `jti`,
THE FIRM holds the identity mapping, and neither side alone can connect a
record to a person. Re-identification requires the firm to act, which puts
the disclosure decision -- and the legal process behind it -- on the party
with the attorney-client relationship. Adding a client identifier is a
breaking change to that posture; the complete field set is pinned by
`test_link_tokens.py` so it cannot be widened quietly.

`employee_id` IS carried, from the minting employee's VERIFIED uid (never the
request body, which could forge attribution). That is what makes the
maintainer's telemetry requirement -- firm, form, and originating employee on
every session -- true for CLIENT sessions, which have no account to read
identity from.

**One form, one completion, two clocks.** The link names one kit and the
socket ENFORCES it: the handshake is client-controlled, so a link holder who
edits `kit_id` is REFUSED, not silently given the right form (a silent
substitution would produce a confirmation record naming a form the client
never saw). ~48h to open from issuance, then SEVEN DAYS to complete from FIRST
OPEN -- the completion clock starts at open, so a client who opens on hour 47
still gets a full window. The 7 days is deliberate (maintainer, 2026-08-24):
a client who loses their work returns to the original message and clicks the
SAME link rather than phoning the firm for a new one. The bound is on
FINISHING, not on how many times they may open it -- a long intake form is
not filled in one sitting, and refusing a reopen creates firm staff work
without preventing any abuse. The client's browser tab also keeps the
credential across a RELOAD (sessionStorage, tab-scoped), so the 7-day
fallback is for a closed tab or a new device, not for an accidental
refresh. One-time use lives in the `link_redemptions` store,
because a signed bearer string is inherently replayable -- and it is enforced
at every door that can cause SPEND: `/api/links/open`, the WebSocket, and the
two `/api/tts/*` routes via `require_paid_client_work`. It is deliberately
NOT enforced on `require_auth`, which gates retrieval -- see the split above.
One shared `enforce_link_redemption` serves every door that does redeem,
EXTRACTED rather than copied: two hand-written versions of a security check
drift, and the drift is
silent. That is not hypothetical here -- the socket redeemed while
`require_auth` did not, so a COMPLETED link kept serving schema, PDF bytes,
`/api/fill-pdf` and both PAID TTS routes for the rest of its ~48h `exp`,
which is the same "enforced only on a door an attacker need not call" hole in
a different place (bd polyglot-pdf-ugm6, Opus cross-surface r1).

**Two different sets, easily conflated.** The count above is the
`require_auth`-GATED set, and `POST /api/links/mint` belongs in it -- it is
`Depends(require_auth)` like the rest. That is NOT the same as the set of
doors a CLIENT credential can open: mint refuses a client, because minting
needs a `uid` and a client has none. When a number here goes stale, fix it
from `test_http_route_auth.py`, which derives the gated set from the shipped
sources -- that test is the authority, not this prose. Reopening an UNFINISHED
link is allowed (a refresh or dropped connection must not strand a client);
only COMPLETION burns it, and only a REAL completion -- an abandoned session
leaves the link usable, because abandonment is the common case on a long form
and burning there would strand a client mid-intake.

**Every refusal is the same 404** -- forged, expired, replayed, suspended
firm, kit no longer allowed. Distinguishable errors would make the
unauthenticated endpoint an oracle for probing which links and firms exist.
Entitlement is RE-CHECKED at open rather than trusted from the mint-time
snapshot, since a firm can be suspended in the 48 hours in between.

**Minting is OFF by default** (`LINK_MINTING_ENABLED`); the spend ceiling it
waited on (bd `polyglot-pdf-ik7e`) has shipped, and BOTH deployed channels now
enable it (demo and staging, bd `polyglot-pdf-hvui4`) --
see [config-deployment.md](config-deployment.md).

Staff mint from `/console/links` (bd `polyglot-pdf-gob8l`), behind
`ProtectedRoute`. The page is only the door: `firm_id` and `employee_id` come
from the VERIFIED token, never from anything the page sends, so a reachable
page cannot grant itself a firm.

### The firm WRITE path: authorization is not authentication

`POST /api/form-kits/{kit_id}/retire` (bd `polyglot-pdf-z6bk9`) is the firm
tier's ONLY write path -- everything else a firm touches is read + telemetry.
`require_auth` gets the caller through the door; it authorizes nothing. THREE
further checks all have to hold, and each refuses a different real attacker:

| Check | Refuses |
|-------|---------|
| `firm_role == "manager"` | An EMPLOYEE of the owning firm. Per the four-level access model, employees send links and track status; they never take a form out of service. |
| `owner_firm_id == <caller's firm_id>` | Another firm -- including one whose allowlist legitimately NAMES this kit. **Visibility is not authorization:** bd `polyglot-pdf-vccy` lets a firm read and fill kits it does not own. |
| `visibility == "private"` | A shared/government form (the maintainer's 2026-08-07 line: a firm retires its own proprietary intake forms, never the shared ones). |

**Retiring does NOT cost the firm its history.** The two archive reads
(`GET /api/form-kits/{kit_id}/archive` + `.../archive/{marker}/schema`) gate on
`require_archive_readable` -- `complete` OR `unpublished` -- while the LIVE
schema/pdf reads still gate on `require_published` (`complete` only). Without
that split, archive-then-retire archived a revision and made it unreachable to
the only party entitled to read it in the same request (bd
`polyglot-pdf-65hgz`, caught by cross-surface review). The VISIBILITY gate is
unchanged and still applies to both, so another firm sees neither.

**Every refusal is a 404, never a 403.** A 403 would confirm the kit exists to
a firm that cannot see it -- the same existence leak the read gates are built
to prevent, so an unauthorized retire is indistinguishable from a kit that was
never there. Retirement is also NOT a delete: it sets `unpublished` (hidden,
write-locked) and archives the revision first, because that revision's bytes
are what its confirmation records were confirmed against. Hard delete stays
guarded and staff-only (bd `polyglot-pdf-6x1j`).

No UI ships with the route: the button belongs to the firm console (bd
`polyglot-pdf-gob8l`), per the maintainer's 2026-08-20 decision -- deliberately
not bolted onto the staff editor.

`GET /api/form-kits/{kit_id}/pdf` is **ungated for PUBLIC kits only** (bd
`polyglot-pdf-vccy` scoped the former blanket non-gate): a public kit's
blank-template bytes ship in the static Hosting bundle regardless, so gating
that read protects nothing — but the route now parses an OPTIONAL bearer token
and 404s a PRIVATE kit for anyone whose `firm_id` claim does not resolve to an
allowlist containing it (invisibility, not 401: the kit's existence is the
secret; an invalid token degrades to anonymous). The catalogue list, the
schema read, AND the fill route's caller-supplied `kit_id` (bd
`polyglot-pdf-vy6id` — the fill read is the fourth client-tier door) enforce
the same firm filter, all through the shared gates in
`backend/services/kit_gates.py`. The public non-gate, the private gate
matrix, and the gated-read SET itself (every client-tier
`load_pdf_bytes`/`load_schema` site must run the gate) are pinned by test so
a blanket-auth sweep — a widening — or a FIFTH ungated read site is a
deliberate decision, not an accident.

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
  (`require_auth` / the WS `?token=` gate). **`firm_id` is consumed** by the
  form-kit routes' firm-scoped visibility filter
  (`backend/routes/form_kit_routes.py`, bd `polyglot-pdf-vccy`) AND by the
  voice path's telemetry: the `/ws/fill` gate keeps its decoded claims and
  keys session + confirmation records on `firm_id` (bd `polyglot-pdf-xwlt`;
  the claim is read from the TOKEN, never the client-controlled handshake).
  `firm_role` is still a future consumer. A stamped claim appears in decoded tokens only on the next
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
fill-pdf/form-kits/schema, the public-kit NON-gate on the kit-PDF GET plus the
private-kit firm-visibility matrix (bd vccy), and the
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
