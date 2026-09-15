# Auth

**Tracks:** frontend/src/firebase/config.ts frontend/src/contexts/AuthContext.tsx frontend/src/components/auth/Login.tsx frontend/src/components/layout/ProtectedRoute.tsx backend/services/auth.py backend/services/firms.py backend/services/kit_gates.py backend/services/link_redemptions.py backend/services/links_store.py backend/services/link_tokens.py backend/services/link_budget.py backend/services/link_spend.py backend/services/credit_ledger.py backend/services/alerts.py backend/services/usage_rollups.py backend/services/runtime_config.py backend/routes/websocket_routes.py scripts/bootstrap_firm.py scripts/grant_credits.py scripts/backfill_firm_kind.py scripts/seed_kit_commercials.py admin_backend/services/admin_auth.py admin_backend/routes/user_routes.py admin_backend/services/user_admin.py backend/routes/form_kit_routes.py scripts/bootstrap_admin_user.py firestore.rules firebase.json backend/services/kit_commercials.py backend/routes/link_routes.py

*Last updated: 2026-09-15 (bd polyglot-pdf-cpsi0: the mint record and the
credit ledger entry each gain an optional human-readable email label
alongside their uid -- `links_store.build_mint_record`'s `employee_email`
and `credit_ledger.append_entry`'s `actor_email` kwarg/entry field. Neither
is validated, required, or a substitute for the uid it rides alongside;
`actor_email` never reaches the `ledger_export` log line. See the mint
record and credit ledger sections below, and Surface contract 34 in
docs/technical_guide.md for the read-side batched resolution
(`admin_backend/services/identity_labels.py`) this bead also adds.)*

*Last updated: 2026-09-09 (bd polyglot-pdf-scaig: a new sibling rule,
`backend/services/firms.py`'s `employee_firm_id(claims)` -- the same shape
as `manager_firm_id`, one role over -- backs a new admin-service dependency,
`admin_auth.require_app_admin_or_owning_manager_or_employee`, scoped to
`GET /admin/firms/{firm_id}/links` only; see "The manager rule" section
below and [admin-service.md](admin-service.md) for the full story of why an
employee-role staff account was previously refused a flat 403 on that route
and why the fix is a new dependency rather than a widening of the existing
composite gate.) (bd polyglot-pdf-w828m: Epic 3 bead E3.4, session-end usage rollups -- new `backend/services/usage_rollups.py`'s `record_session_end()` writes ONE BATCHED `db.batch()` set of `firestore.Increment` updates to `firms/{firm_id}/usage/{YYYY-MM}` and `kits/{kit_id}/usage/{YYYY-MM}` (`connections_ended`, `sessions_completed`, `cost_usd_total`, `links_opened`, `links_completed`, and the `by_kit`/`by_employee`/`by_language`/`by_firm` nested breakdowns), called from the SAME teardown block in `websocket_routes.py` that runs `log_form_session_end`/`_bank_link_spend` (new shared helper `_session_cost_usd()`, extracted so both call sites read the live adapter's cost identically, and `_rollup_language_key()`, which resolves the session's spoken-language name to its BCP-47 code via `language_codes.bcp47_codes_for_spoken_language`, falling back to the raw name for an uncoded language rather than dropping it). `FormFillingService` gains a public `spoken_language()` accessor for the otherwise-private `_spoken_language` the teardown block needs. HYPHENATED MAP KEYS (a kit id like `i-90`, a language code like `zh-CN`): `set(merge=True)` -- chosen over `update()` so the FIRST write of a new month doc creates it -- does NOT dot-expand a flat string key at all (confirmed against the vendored SDK: `DocumentExtractorForMerge` calls `extract_fields` with `expand_dots=False`, unlike `update()`'s extractor), so every nested increment is built as a REAL nested dict via `_nest_increment()`, walking a `FieldPath(*parts).parts` tuple rather than any dotted string. `link_redemptions.py`'s `open_link()` (on the GENUINE first-open branch only, never the idempotent re-open) and `complete_link()` call the module's `record_link_opened`/`record_link_completed` hooks for the two counters `record_session_end` cannot itself produce. `firestore.rules` gains client deny blocks for the two new nested `usage` subcollections, folded into the set-derived rules test.) (bd polyglot-pdf-jecrl: Epic 2 Track A bead A3 -- `POST /api/links/mint` reserves the credit BEFORE signing (one transaction: the `mint_debit` ledger entry, the balance, and the `links[_<channel>]/{jti}` record, via `append_entry`'s `extra_writes`), refuses `403` for a live or kindless firm unless the RAW `LINK_CHANNEL` is exactly `demo` and `402` when `CREDITS_ENFORCED` and the balance will not cover the kit's `credit_cost`; new `backend/services/kit_commercials.py` reads `kits/{kit_id}` fail-soft for that price and the `burn_cap_usd` signed in as `cap_usd`; and `enforce_link_redemption` -- the shared gate serving `/open`, the socket and `require_paid_client_work` -- now refuses (new `LinkNotMinted`, a subclass of `RedemptionUnavailable`) a link with no mint record or a revoked/refunded one.) (bd polyglot-pdf-bo95a: Epic 3 bead E3.5 -- telemetry alert docs, `alerts/{id}` (new `backend/services/alerts.py`), written with DETERMINISTIC ids so a repeat trigger dedups onto the SAME doc: `link_exhausted_{jti}` from `link_spend.check_budget()`'s refusal branch (which now takes an optional `firm_id` kwarg purely to label the alert), and `{firm_id}_credit_low_{day}` / `{firm_id}_credit_exhausted_{day}` from `credit_ledger.append_entry()` after a `mint_debit` commits, compared against the new `CREDIT_LOW_THRESHOLD` runtime-config key (`runtime_config.credit_low_threshold()`, compiled default 10, no env fallback -- same shape as `CREDITS_ENFORCED`). Both hooks are best-effort (alerts.py's own write path can never raise into either caller); `firestore. rules` gains a client deny block for `alerts/{alertId}`, folded into the set-derived rules test.) (bd polyglot-pdf-dmjl5: the firm-manager rule gets ONE home -- `backend/services/firms.py`'s `manager_firm_id(claims)` predicate, consumed by the new `require_firm_manager` dependency in `backend/services/auth.py` (403) and by the retire route's `_require_firm_owns_private_kit` (which keeps its 404); the admin service gains `require_app_admin_or_owning_manager`, its `resolve_target_firm` two-actor rule, and the four staff-account routes that write ONLY `firm_id` and `firm_role`.) (bd polyglot-pdf-1op3g: Epic 2 Track A bead A5 -- `credit_ledger.refund_expired_link()`, the transactional expiry-refund helper keyed on `link_redemptions[_<channel>]/{jti}`'s existence (never the `links` record's best-effort `opened` mirror) and idempotent on `links[_<channel>]/{jti}.status == "minted"`; `reconcile_expired_for_firm()`, the lazy best-effort per-firm catch-up called only by a balance read, never by the mint transaction (pinned by an exact-read-set test on `append_entry()` plus an AST-walk non-call guard); and the socket's `LinkBudgetExhausted` teardown writing a telemetry-only `budget_exhausted` status mirror with no ledger entry.) (bd polyglot-pdf-vnxew: the credit ledger -- `backend/services/credit_ledger.py`'s `append_entry()` is the ONE transactional writer of `firms/{firm_id}.balance_credits` and the only producer of `firms/{firm_id}/ledger/{auto}`; typed signed entries with a snapshotted `firm_kind`, a two-way `usd_amount` rule and a required `reason` on adjustments; a `ledger_export` log line per committed write; and `scripts/grant_credits.py`, the operator grant/adjust CLI on the same helper.) (bd polyglot-pdf-2cwja: documented the FOURTH credential system -- `app_admin`, `admin_backend/services/admin_auth.py` -- alongside the existing three; no code changed in this bead.) (bd polyglot-pdf-4rkrx: Epic 2 data-model bead A1 -- `firms/{firm_id}` gains `kind` (`mock`|`live`, required on create, missing-key treated as live) and `balance_credits`/`balance_updated_at`; `scripts/bootstrap_firm.py` gains a required `--kind`; `link_redemptions.py`'s collection-name helper and the new `backend/services/links_store.py` mint-record store take `channel` as an EXPLICIT argument rather than reading it from the environment; `firestore.rules` gains deny blocks for `kits`, `links`/`links_staging`, `link_redemptions`/`link_redemptions_staging` (fold-in), and the nested `firms/{firmId}/ledger`.) (bd polyglot-pdf-li9x0: `firestore.rules` gains client deny blocks for `admin_audit_log` and `app_config`, and the rules test becomes ONE set-derived test over every Admin-SDK-only collection.) (bd polyglot-pdf-kdp6b: the runtime-config env fallback is a live os.getenv read, so the deploy scripts' LINK_* lines stay in force.) (bd polyglot-pdf-bg313: `LINK_MINTING_ENABLED` moved off a compiled deploy-time default to the runtime-config Firestore doc `app_config/{channel}`, with the deploy-time env var kept as its fallback -- see config-deployment.md.) (bd polyglot-pdf-3q9qn: client links are isolated per channel -- the token carries an `aud` claim naming the channel that may open it.) (bd polyglot-pdf-ah5d3: Epic 2 Track A bead A4 -- the token payload gains an OPTIONAL `cap_usd` per-link spend ceiling, signed in only for a real finite positive number; `link_tokens.py` gains `new_jti()` and a caller-supplied `jti=` on `mint_link_token` so Epic 2 bead A3 can reserve a credit before signing; new `link_budget.cost_ceiling_usd_for_claims(claims)` resolves the socket's spend ceiling with the same defensive parsing as `cost_ceiling_usd_for_kit`; the socket's client-link gate now calls `check_budget` with that resolved ceiling instead of the bare global.) (bd polyglot-pdf-d4wdi: Epic 2 Track A bead A6, the one-time credits migration -- `scripts/backfill_firm_kind.py` gives every pre-A1 `firms/{firm_id}` doc a `kind` (`live` unless named in an explicit `--mock` allowlist) and a `balance_credits`/`balance_updated_at` of 0, ONLY when those keys are absent (never overwrites an operator's deliberate choice), plus an optional one-time `--seed-credits N` `promo_grant` through `credit_ledger.append_entry` for firms newly given a kind; `scripts/seed_kit_commercials.py` writes `kits/{kit_id}` (`credit_cost` from a REQUIRED `--default-credit-cost N`, `burn_cap_usd` from the kit's own `metadata.json` `link_cost_ceiling_usd` where present and valid else `--default-burn-cap-usd`, `display.label`, `updated_by`/`updated_at`) for every kit under `--kits-root` by walking the filesystem directly rather than the async `FormKitStore`; both scripts pin the same DEAD_PROJECTS refusal and `--project`-match assertion as `bootstrap_firm.py`/`grant_credits.py`. `CREDITS_ENFORCED` is switched on per channel only after this has run.). See [the xwlt journal entry](../journal/entries/2026-08-20-bd-xwlt-firm-telemetry.md) for the firm-keyed voice telemetry (the claim's second consumer), [the vccy journal entry](../journal/entries/2026-08-18-bd-vccy-firm-scoped-kit-visibility.md) for firm-scoped kit visibility (the first consumer of the firm claims), [the knmp journal entry](../journal/entries/2026-08-08-bd-knmp-auth-bypass-fail-closed.md) for the fail-closed bypass work, and [the round-8 entry](../journal/entries/2026-08-13-bd-8bjdx-bug-hunt-round-8.md) for the require_auth route enumeration fix.*

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

**Four credential systems now exist, and they must not merge:**

| # | Who | Credential | Where |
|---|-----|-----------|-------|
| 1 | Firm STAFF (voice app) | per-user Firebase ID token + `firm_id`/`firm_role` claims | `services/auth.py` |
| 2 | Schema EDITOR | its own per-user identity (epic `polyglot-pdf-ijntk`) | `services/editor_auth.py` |
| 3 | Firm CLIENT | a signed magic-link token | `services/link_tokens.py` |
| 4 | App ADMIN (admin console) | per-user Firebase ID token + boolean `app_admin` claim | `admin_backend/services/admin_auth.py` |

They are kept apart STRUCTURALLY, not by convention: a link token has ONE
dot, a Firebase JWT has two, so neither verifier can silently accept the
other's token. `/ws/fill` dispatches on that shape (`_verify_ws_credential`),
so a caller cannot opt into the weaker check by labelling their credential.
The fourth system lives on a SEPARATE Cloud Run service entirely (see below),
so it never reaches `/ws/fill`'s dispatch at all -- the separation is by
deployment, not by a shape check.

### App admin -- the FOURTH credential system (bd polyglot-pdf-7w17m)

**Who:** an operator of the app itself (not a firm's staff, not a firm's
client) -- runs the admin console to manage runtime config, read the audit
log, and (in later Epic 2/3/4 beads) firms, credits, and deploys.

**Where it lives, and why it is not a fifth claim on the same token shape
as firm staff.** The admin gate runs on a SEPARATE FastAPI app
(`admin_backend/`, Cloud Run service `polyglot-admin`), not on
`backend/`'s `/ws/fill` or any public-backend route. Mirrors
`backend/services/editor_auth.py`'s shape almost exactly:
`APP_ADMIN_CLAIM = "app_admin"` (a plain boolean -- there is no admin role
gradient, unlike firm staff's `firm_role`), `verify_id_token` with **no**
`check_revoked` (same CLAUDE.md scar #7 reasoning as the other two
verifiers: it would force a Firebase user-record fetch needing
`firebaseauth.users.get`; `admin-backend-sa` actually HOLDS
`roles/firebaseauth.admin` and so could afford it, but it stays off for
symmetry until something measures a need for instant revocation), and the
same 401/403 split with a machine-readable `NO_ADMIN_ACCESS:` prefix
(`NO_ADMIN_ACCESS_PREFIX`) on the "valid account, no admin claim" case --
the same idiom `editor_auth.NO_EDITOR_ACCESS_PREFIX` uses, so a client can
route that specific 403 to a refused screen without string-matching prose.

**Granting access:** `scripts/bootstrap_admin_user.py --email <addr>
--project <p>` is the ONLY way to stamp `app_admin` -- there is no
self-serve signup, and the console's own staff-account routes (bd
`polyglot-pdf-dmjl5`) deliberately CANNOT write this claim: they are
allowlisted to `firm_id` and `firm_role` only, so a console that was
compromised could not mint its own admins. It mirrors
`scripts/bootstrap_editor_user.py`'s `--email`/`--revoke`/`--list` shape and
borrows `scripts/bootstrap_firm.py`'s REQUIRED `--project` (the script
asserts the resolved Firebase project matches it and aborts otherwise,
rather than trusting the operator's gcloud ADC to resolve the right one). It
runs under the operator's OWN gcloud ADC, not the deployed
`admin-backend-sa`.

**Auth project:** the SAME Firebase project as the voice app and the
schema editor (`polyglot-demo-aa709`) -- a separate admin-only project is a
future separation epic's call.

Full route inventory, the service's own IAM envelope, and the console that
consumes this credential are in
[admin-service.md](admin-service.md).

**The `jti` reaches our records, or the split key is not a key.** Both
session events (`form_session_started` / `form_session_ended`) carry
`link_jti` and `employee_id`. Without that column the firm holds one half of
a join with nothing on our side to join to, and the arrangement this whole
design exists to provide -- the firm can re-identify, we cannot -- silently
does not work. `employee_id` on the same records is what makes a CLIENT
session satisfy the telemetry requirement (firm + form + originating
employee) despite there being no account anywhere.

**The token carries `{v, aud, firm_id, kit_id, employee_id, jti, iat, exp,
cw}`, plus an OPTIONAL `cap_usd`, and DELIBERATELY no client identifier.**
(`aud` names the CHANNEL that may
open the link -- an environment, never a person; see bd `polyglot-pdf-3q9qn`.) `cap_usd` (bd `polyglot-pdf-ah5d3` / Epic 2 A4) is a per-link USD
spend ceiling -- a MONEY LIMIT, not a person, so its addition does not touch
the split-key invariant below. It is OPTIONAL: `services/link_tokens.py`'s
`mint_link_token` signs it in only when the caller passes a real, finite,
positive number (bool, NaN, +/-inf, zero and negative are DROPPED rather than
signed in -- there is no way to fix a bad number baked into a signed token,
so "no claim" is the only safe failure). A token minted with no resolvable
kit ceiling, or minted before Epic 2 bead A3 wires `cap_usd` through the mint
route, carries no claim and behaves exactly as a pre-A4 token did. That
absence is the product's legal
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
`link_redemptions.py`'s collection-name resolver takes `channel` as an
EXPLICIT argument (Epic 2 bead A1) rather than reading `LINK_CHANNEL` itself
-- the public backend's own callers (`open_link`/`complete_link`, via
`enforce_link_redemption`) still get the same behavior by omitting the
argument, which defaults to `link_channel()`, but a caller that names a
channel (a future admin-service sweep or reconciler) is no longer silently
redirected to whatever channel the CALLING process happens to be.
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
waited on (bd `polyglot-pdf-ik7e`) has shipped. `LINK_MINTING_ENABLED` is now
a RUNTIME setting resolved from `app_config/{channel}` in Firestore (bd
`polyglot-pdf-bg313`), read at call time rather than compiled in -- with the
deploy-time `LINK_MINTING_ENABLED` env var still live as the fallback for a
channel with no value seeded in Firestore yet -- see
[config-deployment.md](config-deployment.md) for the current mechanism and
fallback order.

Staff mint from `/console/links` (bd `polyglot-pdf-gob8l`), behind
`ProtectedRoute`. The page is only the door: `firm_id` and `employee_id` come
from the VERIFIED token, never from anything the page sends, so a reachable
page cannot grant itself a firm.

**The socket's spend ceiling comes from the TOKEN, not a per-connect kit
read (bd `polyglot-pdf-ah5d3` / Epic 2 A4, closing `polyglot-pdf-4tjt7`).**
Precedence at `/ws/fill`'s client-link gate is `services/link_budget.py`'s
`cost_ceiling_usd_for_claims(claims)`: the token's own `cap_usd` claim wins
over the global default (`LINK_COST_CEILING_USD` via `runtime_config`), and
nothing else -- there is no Firestore kit metadata load on connect. That is
safe because open now REQUIRES a mint record (bd `polyglot-pdf-jecrl` /
Epic 2 A3, below), so every token that can open was signed by the current
mint route and already carries `cap_usd`, resolved once from the kit's
commercial doc. A kit with no resolvable ceiling still signs no claim, and
the global applies -- the defensive default, never "no ceiling". `_verify_ws_credential` carries `cap_usd` through into the
claims dict only when the verified payload has it -- there is no synthetic
`cap_usd: None` for an uncapped link. `websocket_routes.check_budget` still
takes a `kit_metadata`-shaped dict (unchanged signature); the socket now
passes it `{link_budget.KIT_COST_CEILING_KEY: <the already-resolved
ceiling>}`, so `check_budget`'s own parse is a no-op pass over a known-good
number rather than a second, divergent resolution path. `cost_ceiling_usd_for_kit` itself is untouched and still real: A3's mint
route calls it to resolve `cap_usd` from kit metadata in the first place.

**The mint record (`links[_<channel>]/{jti}`, Epic 2 bead A1,
`backend/services/links_store.py`) -- a SEPARATE collection from
`link_redemptions`, answering a different question.** `link_redemptions.py`
answers "has this link been opened/completed" -- written on the CLIENT's
first open. `links_store.py` answers "was this link ever legitimately
minted, by whom, for how much, and is it still good to open" -- written at
MINT time, by staff, before any client sees the link. Folding the two
together would mean a doc exists before the client's first open, which is
precisely the state `link_redemptions.py`'s callers currently treat as proof
of a real open -- so they stay separate collections under the SAME
channel-suffix convention (`links` for demo, `links_staging` for staging).
The doc shape is firm/kit/employee, `credit_cost`/`cap_usd`
snapshots, `minted_at`/`open_deadline`, a `status` cache, and an `expire_at`
for the Firestore TTL policy declared by `scripts/setup-firestore-ttl.sh`.
`build_mint_record()` is the ONE place that shape is defined: the mint
route's transaction writes what it returns with `tx.set()`, and the plain
non-transactional `record_mint()` writes the same builder's output for
callers with no credit to reserve (a migration backfill, a test fixture).
The refund and revoke writers that transition `status` land in Epic 2 bead
A5. **`employee_email` (bd polyglot-pdf-cpsi0)** joins the shape as an
OPTIONAL string -- the minting account's email claim, stamped ALONGSIDE
`employee_id` (the uid), never instead of it; None on a token with no
email claim and on every record written before this bead. The admin
service's read-side batched Auth lookup
(`admin_backend/services/identity_labels.py::labels_for_uids`) resolves a
legacy record's `employee_id` to a label for display; it never backfills
`employee_email` onto the stored document.

`status` is a DERIVED CACHE and never decides money.
`OPEN_BLOCKING_STATUSES` -- `revoked` and `refunded`, the two terminal money
states -- is the closed set the open gate refuses on; `opened` and
`completed` are best-effort mirrors (`mark_opened()` never raises and only
ever moves `minted` -> `opened`), and `budget_exhausted` is telemetry only.
A5's refund transaction reads the AUTHORITATIVE redemption doc, not this
field.

### The credit ledger (`firms/{firm_id}/ledger/{auto}`, Epic 2 bead A2, `backend/services/credit_ledger.py`)

**One helper writes the balance, and nothing else does.**
`credit_ledger.append_entry()` is the only code that writes
`firms/{firm_id}.balance_credits` after the firm is created, and the only
producer of the per-firm ledger subcollection. Subscription grants, prepaid
purchases, promotional grants, mint debits, expiry refunds and operator
adjustments all go through it, so the invariant `balance_credits ==
sum(amount)` holds by construction. Nothing recomputes the balance from the
ledger on a read, so an unlisted writer would break it silently -- the two
deliberate other sites are `firms.upsert_firm()` and
`admin_backend/routes/firm_routes.py`'s create route, each of which
0-initializes the field on first create only, and a set-derived test
(walking both `backend/` and `admin_backend/`) fails on any writer outside
that set.

**The entry.** `type` (one of `subscription_grant`, `purchase`,
`promo_grant`, `mint_debit`, `expiry_refund`, `adjustment`), signed
`amount`, nullable `usd_amount`, a `firm_kind` snapshot, nullable `channel`,
`balance_after`, `actor` (a uid or `system:<origin>`, never blank),
nullable `actor_email` (bd polyglot-pdf-cpsi0: a human-readable label for
`actor`, stamped by the caller when it already has one -- a system actor
passes none, and every entry written before this bead has none either;
NEVER reaches the `ledger_export` log line, per
docs/standards/hipaa-pii-policy.md),
`reason`, `link_jti`, `kit_id`, `ts`. The rules run BOTH ways: `purchase`
and `subscription_grant` REQUIRE `usd_amount` (that is the income figure),
and the other four REFUSE it, because a dollar figure on a promo or a debit
would be double-counted by a view that sums the column. The four
credit-adding types refuse a negative amount, `mint_debit` refuses a
positive one, and `adjustment` -- the one signed escape hatch -- requires a
non-blank `reason`. `firm_kind` is SNAPSHOTTED rather than joined at read
time so a firm later promoted from `mock` to `live` does not retroactively
turn its test grants into revenue, and it falls back to `"live"` on a
missing key, the same fail-closed polarity as `firms.firm_kind()`.

**Reads before writes, nothing hoisted.** This is a Firestore transaction:
every read must precede every write, and the body is RE-RUN on contention.
The balance, the kind snapshot, the sufficiency verdict and `balance_after`
are therefore all computed inside the body from the same snapshot on every
run -- a value read before the transaction would be stale on the retry, and
that retry is exactly the double-mint race (two debits against one credit
leave one entry and a balance of 0). The helper is SYNC on the Admin SDK, so
async callers wrap it in `asyncio.to_thread`.

**Enforcement is a caller's switch, not a default.**
`require_sufficient_balance=False` (the default) WRITES a debit past zero
and lets the balance go negative -- the metered soft-launch mode; `True`
raises `InsufficientCredits` with nothing committed. The mint route passes it from the
`CREDITS_ENFORCED` runtime-config flag and maps the refusal to `402` (below).
It also passes `extra_writes`, which joins the `links[_<channel>]/{jti}` mint
record above to the SAME transaction, so the debit, the entry and the record
commit together or not at all.

**Every committed write emits one `ledger_export` structured log line**
(`event_type`, `type`, `amount`, `usd_amount`, `firm_id`, `firm_kind`,
`channel`, `link_jti`) -- the income and spend feed Epic 3's Cloud Logging
sink filters on. It is emitted AFTER the commit, so an aborted transaction
leaves no line, and it carries no field values, PII or PHI: `reason` is
operator free text and stays out of the log while being stored on the entry.

**`scripts/grant_credits.py`** is the operator CLI on the same helper, so
credits can be granted and rolled back before the console exists. `grant`
(positive only; `--type` promo/purchase/subscription, the paid two requiring
`--usd`) and `adjust` (either sign, `--reason` required) both take a
REQUIRED `--project` whose resolved project is asserted before any write,
refuse the dead project and a zero delta, and support `--dry-run`. Grants
carry no channel, and stamp `actor` as
`system:grant_credits_cli:<operator>` -- deliberately distinguishable from a
console grant's Firebase uid.

### Expiry refund (Epic 2 bead A5, `credit_ledger.refund_expired_link()` + `reconcile_expired_for_firm()`)

**ONE transactional refund helper, keyed on the AUTHORITATIVE redemption
doc, never on the links record's best-effort `opened` mirror.**
`refund_expired_link(db, jti, actor=..., channel=..., now=...)` reads
`link_redemptions[_<channel>]/{jti}` first and refuses
(`LinkNotRefundable(reason="redeemed")`) on its existence ALONE, regardless
of what the doc says: that doc is written on the client's first open and a
failed best-effort `opened` mirror on `links[_<channel>]/{jti}` must never
let a real open through this gate. It then reads
`links[_<channel>]/{jti}` and proceeds only when `status == "minted"`
(`reason="not_minted"` for no record, `reason="not_pending"` for every
other status -- `opened`/`completed`/`revoked`/`budget_exhausted`/
`refunded`); a re-run against an already-refunded jti sees its own prior
`refunded` write and no-ops, which is what makes an hourly sweep (Track B
bead B5, not yet built) and a lazy reconcile racing on the same jti
serialize on Firestore rather than double-crediting. Reuses
`_apply_entry_writes()` -- the write half `append_entry()` itself calls --
so a refund's ledger entry (`type=expiry_refund`, `amount=+credit_cost`
reversing the snapshot taken at mint) is bit-for-bit the same shape as
every other entry, and joins the links record's `status=refunded` flip to
the SAME transaction via `extra_writes`, so a refund can never credit the
firm while leaving `status=minted` for the next sweep pass to hit again.

**`reconcile_expired_for_firm(firm_id, channel=None, now=None)`** is the
LAZY half: queries `links[_<channel>]` for `firm_id == <given>`,
`status == "minted"`, `open_deadline < now`, and calls
`refund_expired_link()` once per hit, logging and skipping (never raising)
a per-link `LinkNotRefundable` so one race lost to the sweep does not 500 a
balance read riding along on it. Called ONLY by the admin-service and
firm-console balance reads, as its own transaction BEFORE the read -- so a
dead Cloud Scheduler job cannot leave a displayed balance visibly wrong --
and NEVER by the mint transaction: `append_entry()`'s own transaction reads
exactly the firm doc (pinned by
`test_append_entry_transaction_read_set_is_exactly_the_firm_doc`, plus an
AST-walk test that neither `append_entry` nor `_apply_entry_writes` ever
calls `reconcile_expired_for_firm`), so when Epic 2 bead A3's mint route
composes its own kit read around this same call, the combined mint
transaction's read set stays exactly `{firm, kit}` with no reconciliation
query riding along on the hottest transaction in the codebase. Not yet
wired into an admin-service route in this bead -- that lands with Track B's
firm/balance read endpoints.

**Opened-but-abandoned links are NOT refunded** (assumed by this bead,
listed in the plan as a maintainer pricing call): a client who opened the
link used the paid session, and the redemption doc's mere existence is
enough to refuse regardless of whether the form was ever finished.

**The socket's `LinkBudgetExhausted` teardown writes a TELEMETRY-ONLY
mirror**, `websocket_routes._mirror_budget_exhausted()`: best-effort,
never-raising, sets `links[_<channel>]/{jti}.status = "budget_exhausted"`
via `links_store._collection()` (off the event loop, `asyncio.to_thread`,
same as every other Firestore call on this route) with NO ledger entry --
whether a budget-exhausted link earns a refund, and whether a replacement
link (bd `polyglot-pdf-1uyof`) costs a fresh credit, are both maintainer
pricing calls the plan lists as undecided.

### Minting a link costs a credit, and opening one requires the record (Epic 2 bead A3, `polyglot-pdf-jecrl`)

**Reserve, THEN sign.** `POST /api/links/mint` runs, in this order:
`link_tokens.new_jti()`; ONE Firestore transaction; then
`mint_link_token(..., jti=..., cap_usd=...)`. The order is the whole
guarantee: a refused reservation must not leave a signed token behind,
because a signed token that opens is a paid Gemini session nobody was
charged for. The transaction is `credit_ledger.append_entry()` -- the repo's
one writer of `balance_credits` -- with the `links[_<channel>]/{jti}` mint
record joined in as `extra_writes`, so the debit, the ledger entry and the
record commit together or not at all. A refusal leaves **no token, no ledger
entry and no record**.

The kit's price comes from `backend/services/kit_commercials.py`
(`kits/{kit_id}`: `credit_cost`, `burn_cap_usd`), read OUTSIDE the
transaction and deliberately fail-soft: a missing doc, an unreachable store
or a malformed value resolves to the global defaults -- never to "free" and
never to "no ceiling". `burn_cap_usd` funnels through
`link_budget.cost_ceiling_usd_for_kit()`, so a bad commercial value fails
exactly the way a bad kit-metadata value does. Both numbers are resolved
ONCE here: `cap_usd` is signed into the token, and both are snapshotted onto
the record, so a later pricing edit cannot change what an already-minted
link costs or may spend. `open_deadline` is pinned to the token's `exp` by
handing `mint_link_token` the same clock -- A5's expiry sweep queries
Firestore on that field, and a drifted deadline would refund a live link or
strand a dead one.

**Two staff-facing refusals, deliberately NOT the uniform 404.** The
uniform-refusal rule protects the UNAUTHENTICATED `/open` door, which must
not become an oracle. This door is authenticated staff and already knows
which firm is calling, so hiding the reason would only cost the console a
useful message.

| Status | When | Notes |
|--------|------|-------|
| `403` | the firm is `live`, **or has no `kind` at all**, and the process's raw `LINK_CHANNEL` is not exactly `demo` | checked INSIDE the transaction, off the same firm snapshot the balance comes from |
| `402` | `CREDITS_ENFORCED` is on and the balance does not cover `credit_cost` | with enforcement OFF the debit is still written and the balance may go negative -- the metered soft-launch mode |
| `503` | no such firm, or the store is unreachable | a deployment/data fault; nothing was committed, so nothing is signed |

**The channel gate reads `os.environ["LINK_CHANNEL"]` RAW, not
`link_tokens.link_channel()`.** `link_channel()` defaults to `demo` so an
unconfigured deploy keeps minting and opening the links it already has --
which means asking it would make an UNSET channel (a laptop, a one-off
container, a misconfigured revision) look like the demo and let it debit a
paying firm. Both halves of that are deliberate and both are pinned: an
unset channel still mints `aud=demo` tokens for **mock** firms, while
refusing live ones. A firm with no `kind` is treated as live, the same
fail-closed polarity `firms.firm_kind()` uses -- a mis-defaulted mock firm
merely blocks staging, a mis-defaulted live firm mints for free. This is
what makes staging-vs-demo firm-billing isolation a CODE property rather
than an operational habit (see
[../doctrine/promotion-tiers.md](../doctrine/promotion-tiers.md)).

**Opening requires that record, and the check lives in the SHARED gate.**
`link_redemptions.enforce_link_redemption()` -- the one helper every door
that SPENDS already calls (`/api/links/open`, `/ws/fill`,
`require_paid_client_work`) -- now reads `links[_<channel>]/{jti}` first and
raises `LinkNotMinted` when there is no record, or when the status is one of
`OPEN_BLOCKING_STATUSES` (`revoked`, `refunded`). Every other status falls
through to the existing redemption gate, so reopening an unfinished link
still works: `opened` and `completed` are best-effort mirrors, and refusing
on them would let a failed mirror write lock a client out of a form they are
part-way through.

Three details carry weight:

- **It runs BEFORE `open_link()`**, which creates the redemption doc.
  Checking after would stamp `opened_at` on a link about to be refused.
- **`LinkNotMinted` subclasses `RedemptionUnavailable`.** The socket gate and
  `require_paid_client_work` both catch a tuple that already includes the
  base class, so a door someone adds later, catching only that, still fails
  closed. A brand-new exception type would have sailed past those handlers
  as an unhandled error.
- **An unreachable links store RAISES** rather than reading as "no record".
  Both refuse; the raise keeps the two causes distinguishable in the log.

All three doors return the refusal they already returned (the uniform `404`
for `/open`, close code `1008` for the socket), so this adds no oracle:
"never minted", "revoked", "already completed" and "store unreachable" stay
indistinguishable from outside. A successful open then best-effort mirrors
the record to `opened` for the console's link table -- advisory, incapable of
failing the request.

**CUTOVER, deliberate:** a token minted before the record existed cannot
open. Few or no live client links exist today (the same reasoning the `aud`
cutover used) and the maintainer re-mints any outstanding link.

### The firm WRITE path: authorization is not authentication

`POST /api/form-kits/{kit_id}/retire` (bd `polyglot-pdf-z6bk9`) is the firm
tier's ONLY write path -- everything else a firm touches is read + telemetry.
`require_auth` gets the caller through the door; it authorizes nothing. THREE
further checks all have to hold, and each refuses a different real attacker:

| Check | Refuses |
|-------|---------|
| `manager_firm_id(claims)` returns a firm | An EMPLOYEE of the owning firm. Per the four-level access model, employees send links and track status; they never take a form out of service. The check is no longer written here: it calls the shared rule (bd `polyglot-pdf-dmjl5`, see "The manager rule" below). |
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

### The manager rule -- ONE home, two refusal shapes (bd `polyglot-pdf-dmjl5`)

"Is this caller a manager, and of which firm?" is decided in exactly one
place: **`backend/services/firms.py`'s `manager_firm_id(claims)`**. It
returns the `firm_id` only when `firm_role` is exactly `"manager"` AND
`firm_id` is a non-empty string; an employee, a dev with no firm, an app
admin, and a client link all get `None`.

**It decides authorization, not authentication.** Handed an unverified dict
it will happily report a manager -- deciding whether the claims are real is
the verifier's job, and doing it twice in two places is how the two
disagree. Every caller passes claims it has already verified.

**Why `firms.py` and not `auth.py`.** Both surfaces need the rule, and
`admin_backend/services/admin_auth.py` may not import
`backend/services/auth.py` -- that module is deliberately liftable, pinned
by
`test_admin_auth.py::test_admin_auth_does_not_import_the_other_two_auth_modules`.
`firms.py` is neither surface's verifier: it is the module that already owns
what a firm IS, and the predicate is pure and side-effect free.
`backend/services/auth.py` **re-exports** the name, so the voice app's own
callers still read it from their own auth module.

**Two consumers, two refusal shapes -- deliberately:**

| Consumer | Form | Refusal |
|----------|------|---------|
| `auth.require_firm_manager` (FastAPI dependency, layered on `require_auth`) | the dependency | **403** -- there is no other firm's resource whose existence a refusal could leak, and a manager-only console page must be able to tell an employee "not your role" |
| `form_kit_routes._require_firm_owns_private_kit` (the retire path) | the predicate | **404** -- a 403 would confirm to a firm that another firm's kit exists |
| `admin_auth.require_app_admin_or_owning_manager` (the composite gate) | the predicate | **403** with the `NO_ADMIN_ACCESS:` prefix, for an account that is neither an admin nor any firm's manager |

The rule is shared; the refusal shape is each caller's own.

**Pinned as a SET, not an instance** (CLAUDE.md scar #8).
`backend/tests/unit/test_require_firm_manager.py` walks every non-test
module under `backend/`, `admin_backend/` and `scripts/` and fails on any
comparison against the literal `"manager"` outside a short justified
allowlist (`firms.py`, which defines it; `bootstrap_firm.py` and
`user_admin.py`, which restate it as a wire contract and are pinned against
the home). So the next route that hand-writes
`claims.get("firm_role") == "manager"` fails CI instead of drifting for a
release.

**The sibling rule, `employee_firm_id` (bd `polyglot-pdf-scaig`).** The
same shape, one role over, lives right beside `manager_firm_id` in
`firms.py`: returns `firm_id` only when `firm_role` is exactly `"employee"`
AND `firm_id` is non-empty, with the identical defensive contract (a
non-dict claims value, an empty-string or non-string `firm_id`, and a
case-sensitive role match all resolve to `None`). Added when the admin
service's link-listing route needed a THIRD actor kind
(`admin_auth.require_app_admin_or_owning_manager_or_employee`, its own
dependency rather than a widening of the composite gate -- see
[admin-service.md](admin-service.md)'s subsection on it for why). Enumerated
over its own whole claim space in `test_require_firm_manager.py`, alongside
a check that `manager_firm_id` and `employee_firm_id` never both accept the
same claims dict.

### Staff-account management on the admin service (bd `polyglot-pdf-dmjl5`)

`POST /admin/users`, `PATCH /admin/users/{uid}/disable`, `PATCH
.../role` and `GET /admin/users` let an **app admin** or a **firm manager**
manage a firm's staff accounts. The gate is
`require_app_admin_or_owning_manager`; the firm comes from the **body/query
for an admin** (required -- 422 if omitted) and from the **verified token
for a manager** (a request that names a firm at all, even their own, is
**403**). Route inventory and the full rationale are in
[admin-service.md](admin-service.md).

**The claims allowlist.** These routes write **only** `firm_id` and
`firm_role` -- never `app_admin`, `schema_editor_role` or `vff_dev`. It is a
property rather than a promise: `user_admin.merge_firm_claims()` builds its
output from `WRITABLE_CLAIMS` plus the account's **existing** claims, so no
request value can reach any other key, and every pre-existing claim survives
(`set_custom_user_claims` **replaces** the whole claims object -- the same
trap `scripts/bootstrap_firm.py` documents as its highest-risk line).
`app_admin` is still granted only by `scripts/bootstrap_admin_user.py`,
under an operator's own credentials.

Creating an account returns a Firebase **password-reset link** for the
console to display; the generated password is never returned or logged, and
**no email is sent** in this epic (planner decision). Every mutation writes
a `pending` audit row before the Firebase Auth call and marks it `committed`
or `failed` after -- Auth mutations cannot join a Firestore transaction, so
a row stuck at `pending` is the signal that the action may have taken
effect.

## Firm identity (`firms/{firm_id}` + custom claims)

The firm tier's identity backbone (bd `polyglot-pdf-lo88`, epic
`polyglot-pdf-02ye`; four-level access model in the
[sprint-19 plan's 2026-08-14 addendum](../sprint_19_firm-tier-kit-lifecycle_plan.md)).

- **Datastore** — Firestore collection **`firms/{firm_id}`** (doc ID =
  operator-chosen slug): `name`, `contact_email`, `allowed_kits: [kit_id]`,
  `status: "active" | "suspended"`, `kind: "mock" | "live"` (Epic 2 bead A1;
  required on create), `balance_credits: int` and `balance_updated_at`
  (also A1; 0-initialized on create, thereafter written ONLY by
  `backend/services/credit_ledger.py`'s single transactional helper (Epic 2
  bead A2 — see "The credit ledger" below) — NOT
  channel-partitioned, one balance per firm regardless of which channel's
  mint debits it, safe only because a `live` firm can mint only on the
  explicit demo channel), `created_at`/`updated_at`. Accessed ONLY via
  the Admin SDK through `backend/services/firms.py`; `firestore.rules` carries
  an explicit `firms/**` client deny block as defense in depth (the Admin SDK
  bypasses rules, so the block grants nothing — it forecloses any future
  client-SDK path), plus its own block for the nested `firms/{firmId}/ledger`
  subcollection (Epic 2 bead A2's ledger rows; a parent's deny does not
  cascade to a subcollection in Firestore's rules language).
- **Read contract — FAIL CLOSED, in BOTH directions now.**
  `firms.get_allowed_kits(firm_id)` returns
  `[]` on every failure branch (store disabled via `FIRMS_FIRESTORE_ENABLED`,
  missing firm, non-active status, malformed doc, read error) — the deliberate
  inverse of the confirmation sink's fail-open writes, because a broken firms
  store must never widen private-kit visibility (consumer: bd
  `polyglot-pdf-vccy`). `firms.firm_kind(firm_id)` (Epic 2 bead A1) fails
  closed the OPPOSITE way — every failure branch, AND a doc with no `kind`
  key at all (the window between this bead's deploy and the backfill
  migration, bd `polyglot-pdf-d4wdi`), resolves to `"live"`, because widening
  who mints without the live-firm demo-channel gate is the risk there, not
  narrowing kit visibility. `firms_store_status()` is the read-shaped health
  probe for diagnosing fail-closed silence on either reader.
- **Staff identity** — `firm_id` + `firm_role` (`manager` | `employee`) custom
  claims on the staff member's normal Firebase account, stamped by the admin
  bootstrap script below. The claims ride the existing ID-token verification
  (`require_auth` / the WS `?token=` gate). **`firm_id` is consumed** by the
  form-kit routes' firm-scoped visibility filter
  (`backend/routes/form_kit_routes.py`, bd `polyglot-pdf-vccy`) AND by the
  voice path's telemetry: the `/ws/fill` gate keeps its decoded claims and
  keys session + confirmation records on `firm_id` (bd `polyglot-pdf-xwlt`;
  the claim is read from the TOKEN, never the client-controlled handshake).
  **`firm_role` is consumed** by the manager rule,
  `backend/services/firms.py`'s `manager_firm_id(claims)` (bd
  `polyglot-pdf-dmjl5`) -- the ONE home for "which firm does this caller
  manage", read by the retire route and by the admin service's staff-account
  routes (see "The manager rule" below). A stamped claim appears in decoded
  tokens only on the next
  token refresh (up to ~1h; force via sign-out/in or `getIdToken(true)`).

**The admin step** (creates/updates the firm record and stamps staff claims;
full usage, `--dry-run`, and the exit-code contract live in the script
docstring):

```bash
backend/.venv/Scripts/python.exe scripts/bootstrap_firm.py acme-legal \
    --name "Acme Legal Aid" --contact intake@acme-legal.example \
    --allowed-kits w7,i-90 \
    --kind live \
    --manager-email ada@acme-legal.example \
    --employee-email bo@acme-legal.example \
    --project polyglot-demo-aa709
```

`--kind` is REQUIRED (Epic 2 bead A1; no default, on purpose — see
`firm_kind()`'s fail-closed direction above for why an implicit default in
either direction is wrong). Local minting needs the dev account's own firm
created with `--kind mock`.

Rules for the Admin-SDK-only collections — `firms/{firmId}` and the nested
`firms/{firmId}/ledger/{entryId}`, `admin_audit_log/{rowId}`,
`app_config/{channel}`, `kits/{kitId}`, `links/{jti}` + `links_staging/{jti}`,
and `link_redemptions/{jti}` + `link_redemptions_staging/{jti}` (the ledger,
kits, links and link_redemptions blocks all added by Epic 2 bead A1;
`admin_audit_log`/`app_config` by bd `polyglot-pdf-li9x0`) — reach the live
project only via a frontend/full deploy or an explicit
`firebase deploy --only firestore:rules --project polyglot-demo-aa709` — a
backend-only deploy does NOT ship rules. Note that `firestore.rules` is
**project-wide**, so it is a demo action whichever channel you ran it from
(staging and the demo share the project). Manual verify of a deny: from a
signed-in browser console, a client-SDK
`getDoc(doc(db, "admin_audit_log", "x"))` must return `permission-denied`, and
likewise for `firms`, `app_config`, and the newer collections above.

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
`backend/tests/unit/test_firms_service.py` (fail-closed reads in BOTH
directions -- `get_allowed_kits` to `[]`, `firm_kind` to `"live"` -- upsert
idempotency, and the `balance_credits=0`/`kind` seeding on first create),
`backend/tests/unit/test_bootstrap_firm_cli.py` (claims merge,
role stamping, wrong-project abort, dead-project refusal, `--kind`
required with no default and flowing through to `upsert_firm` unchanged),
`backend/tests/unit/test_link_redemptions.py` (one-time-use plus the
channel-explicit-argument contract: a caller naming no channel gets
`link_channel()`'s default, a caller naming one is never silently overridden),
`backend/tests/unit/test_links_store.py` (the mint-record schema, its own
channel-naming contract mirroring `link_redemptions.py`'s, the `record_mint`
input guards, and the `expire_at` TTL derivation), and
`backend/tests/unit/test_firestore_rules_text.py`, which since bd
`polyglot-pdf-li9x0` is ONE set-derived test over EVERY Admin-SDK-only
collection rather than a single assertion about `firms/**`: the list lives in
one constant (`ADMIN_SDK_ONLY_COLLECTIONS` — now `firms`,
`firms/{firmId}/ledger`, `admin_audit_log`, `app_config`, `kits`, `links`,
`links_staging`, `link_redemptions`, `link_redemptions_staging`), a later bead
extends the LIST rather than
adding another copy of the assertion, and the test fails in both directions —
a listed collection with no deny block, and a deny block for a collection
nobody listed. It also rejects a WEAKENED block (one that keeps
`allow read, write: if false;` but adds a second `allow`), not only a deleted
one. The nested `firms/{firmId}/ledger` entry is matched by a widened
both-directions regex that allows one extra `/{wildcard}/segment` hop, since
a parent's deny does not cascade to a subcollection and the nested block
needs its own list entry and its own round-trip against the file.
`frontend/src/contexts/AuthContext.test.tsx` covers
`AuthContext` (the authorized_emails allowlist gate, sign-in/out/reset delegation,
the loading lifecycle, and the test-harness bypass) and `ProtectedRoute` (both gate
states). There are no tests yet for `Login` (the form/UI component itself).
See [../standards/testing.md](../standards/testing.md).
