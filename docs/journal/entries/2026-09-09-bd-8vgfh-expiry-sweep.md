---
date: 2026-09-09
bead: polyglot-pdf-8vgfh
title: "feat(admin): B5 expired-link sweep endpoint + require_google_oidc + Cloud Scheduler declaration"
sprint: 22
tags: [security, testing]
---

## Trigger

Epic 2 Track B bead B5 of the admin-console program
([plan](../../sprint_22_admin-console_plan.md), "Refund on unopened
expiry"). Bead A5 (bd `polyglot-pdf-1op3g`, closed) built the transactional
refund helper but deliberately left its scheduled caller out of scope --
"the hourly sweep, Track B bead B5, NOT this bead." Without a caller,
`credit_ledger.refund_expired_link()` would never run outside a firm's own
lazy balance read, and an unopened link would sit un-refunded until
something touched that firm's balance page. This bead is that caller: the
route, its machine-caller gate, and the Cloud Scheduler job that invokes it
hourly.

## What shipped

**`POST /admin/links/sweep-expired`** (`admin_backend/routes/
sweep_routes.py`). Optional `?channel=` sweeps one channel (404 on an
unknown value); omitted, sweeps every channel in `KNOWN_CHANNELS`. Per
channel, queries `links[_<channel>]` for `status == minted AND open_deadline
< now` (no `firm_id` filter -- unlike A5's firm-scoped
`reconcile_expired_for_firm`, this sweep is cross-firm by design) and calls
`credit_ledger.refund_expired_link()` once per hit. A per-link
`LinkNotRefundable` or store hiccup is logged and skipped, never aborting
the whole hourly pass. Returns counts only
(`{results, total_refunded, total_skipped}`) -- per-link detail already has
a durable home in the ledger entry and the audit row, so returning it a
third time in the response would just be a copy that can drift.

**`require_google_oidc(audience, allowed_caller_emails)`**
(`admin_backend/services/admin_auth.py`), the fourth and last gate the plan
named. A FACTORY, not a plain dependency -- both arguments vary per route
and per deployment, and both accept a zero-arg callable resolved fresh on
every request rather than once at import time (the real values come from
`ADMIN_SERVICE_URL`/`SWEEP_SCHEDULER_SA_EMAIL`, deploy-time env vars that
do not exist when the route module imports at process start). The gate
checks BOTH the token's `aud` claim (via `google.oauth2.id_token.
verify_oauth2_token`) and its `email` claim against an explicit allowlist
-- audience alone is forgeable by anyone with a GCP project on a public
(`--allow-unauthenticated`) service, so a matching audience proves only
"Google vouches this token was minted for this URL," never "this is the
caller I expect." 401 for a token that fails verification outright; 403
for one that verifies but names an unlisted caller; 503 when verification
itself could not run, or when the route's own configuration (an empty
audience or empty allowlist) is incomplete -- fail CLOSED, never read
"nothing to check" as "allow it."

One mechanical wrinkle worth naming: `require_google_oidc`'s returned
closure is explicitly renamed to `"require_google_oidc"`
(`_dependency.__name__ = "require_google_oidc"`) before being returned.
`test_admin_route_auth.py`'s route/gate set pin reads a dependency's bare
`__name__` to learn which of the four known gates a route carries; left as
Python's default inner-function name, a route wired through this factory
would look ungated to that test. Every other gate in this module IS its
own name; this is the one exception, and both `test_google_oidc_gate.py`
and `test_admin_route_auth.py` pin the rename directly (mutation-verified:
deleting the rename line reddens both, plus the set pin itself, which
starts reporting the sweep route as carrying zero known gates).

**`credit_ledger.refund_expired_link()` gains an optional `extra_writes`
parameter**, mirroring `append_entry`'s own. Epic 2 criterion 5 requires
every mutating admin route to audit in the required form, and the sweep's
refund IS a mutation on this service -- but the transaction it needs to
join lives in `backend/services/credit_ledger.py`, outside
`admin_backend/`. `extra_writes` is the seam: `sweep_routes.py` builds a
closure that calls `audit_log.record_in_transaction`, and
`refund_expired_link` composes it after its own internal
`_mark_refunded` write so both land in the SAME Firestore transaction as
the balance/entry writes. `credit_ledger.py` is not in this bead's declared
surfaces, but the extension is additive-only (new optional kwarg, `None`
default, zero behavior change for existing callers) and directly required
by the plan's own audit criterion -- a small, obvious change in service of
the bead, not a new commitment.

**`test_admin_audit_coverage.py` gains `MUTATION_KIND_DELEGATED_
FIRESTORE`.** The existing coverage test's "is this call inside a
`@firestore.transactional` body" check assumes the transaction and the
audit call live in the SAME module -- true for every existing route, false
here. The new kind's static proxy: does this module define a closure
calling `record_in_transaction`, AND pass that closure BY NAME as
`extra_writes=` at some call site in the same module. Backed by a genuine
runtime proof rather than resting on the AST alone:
`test_sweep_routes.py::test_a_forced_audit_failure_leaves_the_refund_
uncommitted` forces the audit write to raise and asserts NEITHER the
balance nor the links status changes -- mirroring `test_config_routes.py`'s
own forced-audit-failure pin for the plain in-module form.

**`scripts/setup-admin-service.sh`** gains the `cloudscheduler.
googleapis.com` API enable (with its first consumer, this bead's job) and
a NEW, separate `admin-sweep-scheduler-sa` service account -- deliberately
NOT `admin-backend-sa`, since `require_google_oidc`'s whole point is
pinning a caller identity distinct from the service's own callee identity;
reusing one account for both directions would let a single compromised
credential both act as the admin service and trigger it. The
`gcloud scheduler jobs create http admin-sweep-expired-links` command
(hourly, `--oidc-service-account-email` + `--oidc-token-audience` both
pinned to this bead's identities) is printed as an operator NOTE, not run
-- it needs the admin service's own Cloud Run URL, which does not exist
until after that service's first deploy. Pinned by the new root-level
`tests/test_setup_admin_service_scheduler.py`, the sibling of
`tests/test_setup_firestore_ttl_script.py`'s shipped-script-text pattern
for an operator script nothing in CI ever executes.

**Deliberately NOT in this bead:** actually creating the Cloud Scheduler
job or running `setup-admin-service.sh` against a real project (both
operator actions, PENDING-DEPLOY); Epic 4 4.3's Pub/Sub push route, the
gate's second consumer.

### Cross-surface review round (fixes)

The Opus outer cross-surface review returned `GAPS-FOUND (3)` on the first
pass, all three ADOPTED (fixed inline, no maintainer decision needed) plus
one nit already filed as its own bead by the reviewer:

- **ADOPTED -- missing composite index for the sweep's own query.** The
  sweep's `status == minted AND open_deadline < now` query has no `firm_id`
  filter (unlike A5's `reconcile_expired_for_firm`), so the ONE composite
  index this bead shipped (`firm_id, status, open_deadline`) cannot serve
  it -- Firestore only serves a query from an index whose fields are a
  PREFIX of the query's constrained fields. Every hourly sweep would fail
  at runtime with `FAILED_PRECONDITION` while the suite stayed green (the
  test fake filters in Python). Fixed: two new `(status, open_deadline)`
  composite indexes in `firestore.indexes.json` (one per collection,
  `links` and `links_staging`), plus `test_firestore_indexes.py` extended
  to guard the new query alongside the old one -- the guard now identifies
  a shipped index by its FIELD-NAME SET rather than by collectionGroup
  alone, since two legitimately different queries now share each links
  collection.
- **ADOPTED -- OIDC audience mismatch between the scheduler job and the
  gate.** `scripts/setup-admin-service.sh`'s printed scheduler-job command
  pins `--oidc-token-audience` to the service root PLUS the route's own
  path, but `sweep_routes._audience()` was returning the bare
  `ADMIN_SERVICE_URL` env var (the service root only) with nothing
  appended -- so a real Cloud Scheduler token's `aud` claim would never
  match what the gate checked, and every scheduled call would 401. Fixed:
  `_audience()` now appends the route's own fixed path
  (`/admin/links/sweep-expired`) to the bare `ADMIN_SERVICE_URL`; the test
  fixture that had set `ADMIN_SERVICE_URL` to the FULL path (silently
  masking the exact mismatch the reviewer caught) is corrected to the bare
  root; new tests pin `_audience()`'s exact composition and cross-check it
  against the setup script's own shipped text so the two sides cannot
  silently diverge again.
- **ADOPTED -- a hand-run env-var step that the next deploy silently
  erased.** `deploy-admin.sh`'s Cloud Run deploy uses `--set-env-vars`,
  which REPLACES the service's entire env block. `ADMIN_SERVICE_URL` and
  `SWEEP_SCHEDULER_SA_EMAIL` were documented as a SEPARATE, one-time
  `gcloud run services update --update-env-vars` step an operator ran by
  hand -- so the very next `./deploy-admin.sh` run wiped that binding,
  fail-closing the sweep route (503) with no test or alert able to notice.
  Fixed: both values are now computed INSIDE `deploy-admin.sh` itself
  (`SWEEP_SCHEDULER_SA_EMAIL` is constructible from the setup script's
  fixed `SCHEDULER_SA_NAME` literal with no lookup needed;
  `ADMIN_SERVICE_URL` is looked up via `gcloud run services describe`
  BEFORE the deploy call, tolerating the true-first-deploy case where the
  service does not exist yet) and folded into the same `BACKEND_EXTRA_ENV`
  the CORS origins already travel through -- every deploy re-asserts both
  vars instead of a separate step a later deploy can erase. New test file
  `tests/test_deploy_admin_sweep_env_vars.py` pins the computation and the
  wiring into `BACKEND_EXTRA_ENV`; `scripts/setup-admin-service.sh`'s
  printed NOTE no longer instructs the now-unnecessary manual step.
- **FILED, not fixed here** -- `docs/sprint_22_admin-console_plan.md`'s
  "runs per channel with the channel passed explicitly" line describes a
  per-channel Scheduler job; the shipped script declares ONE job that
  sweeps every channel in one request. A defensible simplification with a
  real operational tradeoff (one slow channel now delays the other; a
  Scheduler retry can't attribute failure to a channel), needing a plan
  reconciliation rather than a code fix -- filed as bd `polyglot-pdf-2n1qs`
  by the reviewer, left open.

All three fixes were mutation-verified (the pre-fix behavior was
reconstructed and confirmed to fail the new/changed test red, then the fix
was restored and confirmed green) before this round closed. Full backend
suite (3530 passed, 72 skipped) and root suite (1442 passed, 46 skipped)
both green after the round.

### Cross-surface review round 2 (fixes)

The Opus outer cross-surface review returned `GAPS-FOUND (2)` on the
second pass. Both blockers ADOPTED (fixed inline); four other findings
FILED (none blocking, per the reviewer's own classification), no
maintainer decision needed for any of them.

- **ADOPTED (blocker) -- the 401-vs-503 transport-failure classifier was
  unreachable in production; every real certs-fetch outage misclassified
  as 401.** `_verify_google_id_token`'s classifier caught only builtin
  `(ConnectionError, TimeoutError)`, but `google.auth.transport.requests.
  Request.__call__` wraps every real transport failure (a DNS failure, a
  non-200 certs response, or a wrapped raw `requests.exceptions.
  ConnectionError`) as `google.auth.exceptions.TransportError`, which
  chains from `GoogleAuthError -> Exception`, NOT from builtin
  `ConnectionError` -- and a raw `requests.exceptions.RequestException`
  chains from `OSError`, also not builtin `ConnectionError`. So an outage
  in Google's certs endpoint was returned to Cloud Scheduler as 401
  "Invalid or expired sign-in" instead of 503 "identity verification
  unavailable," contradicting the code's own docstring, `docs/components/
  admin-service.md`, and the bead's design intent (Cloud Scheduler retries
  a 503 on its own backoff; retrying a 401 forever never succeeds). Fixed:
  the classifier now also catches `google.auth.exceptions.TransportError`
  and `requests.exceptions.RequestException`/`OSError` explicitly. Two new
  tests in `test_google_oidc_gate.py` monkeypatch the REAL
  `google.oauth2.id_token.verify_oauth2_token` call (one level deeper than
  the existing `_fake_verify` seam) to raise each real exception shape and
  assert `OidcVerificationUnavailable`; a third test guards the other
  side, confirming a genuine `ValueError` (bad signature/audience) still
  maps to 401 and was not swallowed by the widened catch. Mutation-verified:
  reverting the classifier tuple to `(ConnectionError, TimeoutError)`
  reddened both new positive tests while the guard test stayed green;
  restoring the fix returned all 16 gate tests to green.
- **ADOPTED (blocker) -- `docs/components/config-deployment.md` still said
  `require_google_oidc` "is still ahead," a fact this same bead falsifies.**
  The file's gate-inventory paragraph said three of the four gates existed
  and `require_google_oidc` was not yet shipped; this bead ships it with
  its first consuming route, so all four now exist. `admin_backend/main.py`'s
  docstring and `docs/components/admin-service.md` were both already
  correct ("ALL FOUR now exist"); this third restatement of the same fact
  (CLAUDE.md scar #8 shape) was the one left stale. Fixed: corrected to
  "ALL FOUR now exist," named the sweep route as the first consumer, and
  cross-referenced `admin-service.md` for the route table rather than
  duplicating it. Grepped the repo for any other "still ahead" / "Three now
  exist" restatement of this fact -- none found, so this was the only
  instance.
- **FILED, not fixed here** -- `admin_backend/routes/sweep_routes.py`'s
  module docstring says its two env vars are read at IMPORT time; they are
  actually read PER-REQUEST via callables, as the module's own inline
  comment two hundred lines down already states correctly. A doc-only
  self-contradiction with no behavior at stake. Filed bd `polyglot-pdf-dct3a`.
- **FILED, not fixed here** -- the sweep route's audit row hardcodes
  `actor_email=None` even though `require_google_oidc` has already
  verified and returned the caller's service-account email; every other
  mutating admin route passes `actor.email`. The one route whose gate
  exists specifically to establish which machine identity called is the
  one route that then drops it from its own audit trail. Filed bd
  `polyglot-pdf-qrkps`.
- **FILED, not fixed here** -- `deploy-admin.sh`'s env-var enumeration is
  missing from `docs/components/config-deployment.md`'s own list (an
  incomplete list, not a false claim, so not a blocker). Filed bd
  `polyglot-pdf-mzd48`.
- **FILED, not fixed here (unverified, not confirmed broken)** --
  `email_verified is True` is asserted only against hand-built mock
  claims in every existing test; whether a REAL Cloud Scheduler-minted
  OIDC token actually carries that claim was not settled (the reviewer's
  local `gcloud` auth was a user account, which service-account
  impersonation for a probe rejects). Likely fine (Google's documented SA
  ID tokens do carry it) but unverified, and the exact scar #7 shape (a
  mock proves the code checks, not that the issuer sends). Filed bd
  `polyglot-pdf-v5ee9` with the impersonation command to settle it before
  the first real deploy of this route.

Both blocker fixes were mutation-verified. Full backend suite
(3530 passed, 72 skipped), root suite (1442 passed, 46 skipped), and the
full admin_backend suite (260 passed) all green after this round.

## Lessons

**A shared helper's `extra_writes` hook is the load-bearing seam for
cross-package audit requirements, not a workaround.** The plan's audit
criterion (every mutating admin route audits in-transaction) reads as a
same-package concern, but the mutation this route performs is owned by a
DIFFERENT package's transactional helper. Extending that helper's own
extension point (rather than duplicating its transaction locally, or
weakening the audit form to fire-and-forget) keeps the atomicity guarantee
real and keeps the transaction in ONE place. The general form: when a
route's mutation is delegated to a shared helper, look for that helper's
existing composition seam before inventing a parallel one.

**A same-module AST assumption in a coverage test is itself a contract
that needs updating, not worked around.** `test_admin_audit_coverage.py`'s
`_calls_inside_transactional_bodies` walks ONE module's AST on the
assumption that a route's transaction is always its own -- true until a
route's mutation is delegated elsewhere. Rather than contort the sweep
route to fake a local transactional wrapper (dishonest -- there is no
second transaction), the test's own vocabulary was extended with a new,
honestly-named mutation kind and a real runtime proof to back the weaker
static check. The alternative (skip the coverage test for this one route)
would have left Epic 2 criterion 5 unpinned for its first exception.

**A factory-returned FastAPI dependency needs its `__name__` set
deliberately when other tests key on bare function identity.** Three of
the four admin-service gates are plain functions FastAPI wires directly
(`sub.call is require_app_admin` works); `require_google_oidc` is a
factory, so the object FastAPI actually wires is an anonymous inner
closure. A test asserting gate identity by name silently degrades to "this
route carries some dependency" the moment a factory is introduced, unless
the closure is explicitly named to match its factory -- worth flagging
generally: any future factory-shaped gate in this vocabulary needs the
same rename, and the two tests here (one at the gate level, one at the
route level) are the pattern to copy.

## Doc freshness

- `docs/components/config-deployment.md` -- round 2 fix: gate-inventory
  paragraph corrected to "ALL FOUR now exist" (was falsified by this same
  bead); stamp bumped to 2026-09-08.
- `docs/components/admin-service.md` -- Tracks line gains
  `admin_backend/routes/sweep_routes.py`; new dated entry; routes table
  row; new `require_google_oidc` section (mirroring the `require_app_
  admin` section's shape); Service account section gains the dedicated
  scheduler SA; Testing section lists the two new test files. Stamp
  bumped to 2026-09-09.
- `docs/technical_guide.md` -- Admin service routes table gains the sweep
  route's row (sorted correctly between `/admin/config/{channel}` and
  `/admin/users`); Surface contract 15 (admin audit log) gains the
  `MUTATION_KIND_DELEGATED_FIRESTORE` explanation. No header stamp by
  design (this doc carries none).
- Every OTHER doc `check_doc_freshness.py` flagged STALE (`auth.md`,
  `config-deployment.md`, `websocket-routing.md`, `voice-ai.md`, and
  roughly twenty more) tracks files this branch never touched
  (`backend/routes/websocket_routes.py`, `backend/adapters/
  live_ai_gemini.py`, the deploy scripts, `backend/config.py`) -- all
  modified 2026-09-02/03 by unrelated prior commits on `dev`. Reviewed and
  left alone.
- No CLAUDE.md change. No `firestore.rules` change (no new collection;
  `links[_<channel>]` and `admin_audit_log` already carry their deny
  blocks).

## Files touched

- `admin_backend/routes/sweep_routes.py` (new) -- the sweep route, its
  per-channel query, and the audit closure.
- `admin_backend/services/admin_auth.py` -- `require_google_oidc`,
  `GoogleServiceActor`, `OidcVerificationUnavailable`,
  `_verify_google_id_token`.
- `admin_backend/main.py` -- registers `sweep_routes.router`.
- `admin_backend/tests/unit/test_google_oidc_gate.py` (new) -- the gate's
  own contract in isolation.
- `admin_backend/tests/unit/test_sweep_routes.py` (new) -- the route end
  to end through a fake Firestore, including the race and forced-failure
  atomicity pins.
- `admin_backend/tests/unit/test_admin_route_auth.py`,
  `admin_backend/tests/unit/test_admin_audit_coverage.py` -- extended for
  the new route and the new delegated-transaction mutation kind.
- `backend/services/credit_ledger.py` -- `refund_expired_link`'s new
  `extra_writes` parameter.
- `backend/requirements.txt` -- `google-auth==2.53.0` pinned explicitly
  (previously only a transitive dependency of `firebase-admin`).
- `scripts/setup-admin-service.sh` -- `cloudscheduler.googleapis.com`,
  `admin-sweep-scheduler-sa`, the printed job-create command.
- `tests/test_setup_admin_service_scheduler.py` (new) -- the script-text
  pins for the scheduler declaration.
- `docs/components/admin-service.md`, `docs/technical_guide.md` -- as
  above.

**Cross-surface review round additions:**

- `firestore.indexes.json` -- two new `(status, open_deadline)` composite
  indexes (`links`, `links_staging`) for the sweep's own query.
- `admin_backend/tests/unit/test_firestore_indexes.py` -- extended to guard
  the sweep's query alongside `reconcile_expired_for_firm`'s, keyed on
  field-name SET rather than collectionGroup alone.
- `admin_backend/routes/sweep_routes.py` -- `_audience()` now appends the
  route's own path to the bare `ADMIN_SERVICE_URL` service root.
- `admin_backend/tests/unit/test_sweep_routes.py` -- fixture corrected to
  set `ADMIN_SERVICE_URL` to the bare root (was silently masking the
  mismatch); new tests pinning `_audience()`'s composition and its
  cross-check against the setup script's shipped text.
- `deploy-admin.sh` -- computes and forwards `ADMIN_SERVICE_URL` /
  `SWEEP_SCHEDULER_SA_EMAIL` through `BACKEND_EXTRA_ENV` on every run.
- `tests/test_deploy_admin_sweep_env_vars.py` (new) -- pins the computation
  and the durable wiring into `BACKEND_EXTRA_ENV`.
- `scripts/setup-admin-service.sh` -- corrected `--oidc-token-audience`
  comment; removed the now-unnecessary manual update-env-vars NOTE.
- `docs/technical_guide.md` -- sweep route's audience description
  corrected (service root + path, not the bare env var).

**Cross-surface review round 2 additions:**

- `admin_backend/services/admin_auth.py` -- `_verify_google_id_token`'s
  classifier now catches `google.auth.exceptions.TransportError` and
  `requests.exceptions.RequestException`/`OSError` alongside the builtin
  `ConnectionError`/`TimeoutError`, so a real certs-fetch transport failure
  is classified as `OidcVerificationUnavailable` (503) instead of falling
  through to `ValueError` (401); docstring corrected to match.
- `admin_backend/tests/unit/test_google_oidc_gate.py` -- three new tests
  against the real `google.oauth2.id_token.verify_oauth2_token` seam:
  `TransportError` and a raw `requests.exceptions.ConnectionError` both
  pin `OidcVerificationUnavailable`; a genuine `ValueError` still pins 401.
- `docs/components/config-deployment.md` -- gate-inventory paragraph
  corrected from "three of four, `require_google_oidc` still ahead" to
  "all four now exist," naming the sweep route as the first consumer.

Review outcomes recorded in the closeout ping.
