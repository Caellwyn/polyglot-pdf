---
date: 2026-09-15
bead: polyglot-pdf-21m1y
title: "fix(tests): backend tests reach the real shared Firestore through ADC -- guard the suite and purge the test artifacts"
sprint: 22
tags: [testing, security, postmortem]
---

## Trigger

The maintainer reported "alerts seem to be duplicating" in the admin console
(2026-09-15). Investigation found the shared project `polyglot-demo-aa709`
holding 149 `alerts` docs (138 `link_exhausted` for firm "firm-a", 10
`credit_low`/`credit_exhausted` for firm "acme" with balance -1, one
`link_exhausted_jti-a`), a `link_redemptions` doc for firm-a, a
`firms/firm-a/usage` rollup doc, and 19 `links` docs with no `firm_id` --
every one of them a TEST ARTIFACT. Root cause: `backend/services/auth.py`'s
`get_db()` (used by `alerts.py`, `usage_rollups.py`, `link_redemptions.py`,
`links_store.py`, `credit_ledger.py`) lazily initializes `firebase_admin`
with ADC and constructs a real `google.cloud.firestore.Client` the moment an
unpatched test exercises one of those stores. On a developer machine with
working gcloud ADC and a quota project, that is not a fake -- it is a live
connection to the shared demo project. CI never showed this because CI has
no credentials to make the same mistake.

Plan: `docs/sprint_22_admin-console_plan.md` (Epic 3 telemetry/alerts).

## What shipped

**The guard.** An autouse `_no_real_firestore` fixture, added to both
`backend/tests/conftest.py` and `admin_backend/tests/conftest.py`, patches
two named targets to raise a loud `RealFirestoreReachedInTest` instead of
succeeding: `firebase_admin.initialize_app` and
`google.cloud.firestore.Client.__init__`. Both are needed -- reading
`firebase_admin`'s own source confirmed `firebase_admin.firestore.client()`
(what `get_db()` calls) resolves the default app, initializing one with ADC
if `backend/services/auth.py`'s own bare module-import-time
`initialize_app()` call hadn't already succeeded, then constructs exactly
`google.cloud.firestore.Client(credentials=..., project=..., database=...)`.
Guarding only `initialize_app` would miss the case (confirmed live on this
machine) where that module-import-time call already created a real app
*before any fixture runs* -- collection happens before fixtures -- so a
later `get_db()` call in the same process skips `initialize_app` entirely
and goes straight to constructing a client. The shared implementation lives
in `backend/tests/unit/_no_real_firestore.py` and is imported by both
conftest files (matching this repo's own "one implementation, not several"
convention -- `admin_backend` already imports from `backend.services.*` for
identical reasons), rather than being duplicated. Opt-out is the existing
`@pytest.mark.external` marker.

**The one offender.** Running the full `backend/tests` and `admin_backend/
tests` suites with the guard active found exactly ONE test reaching the real
path: `test_access_matrix.py::test_no_admin_route_accepts_a_client_link_
shaped_token`, which deliberately calls the REAL `fb_auth.verify_id_token`
(not a fake) to prove a malformed token fails verification, and
`admin_auth.verify_admin_token` self-initializes `firebase_admin` with ADC
when no app exists. Fixed by pre-seeding a real `firebase_admin.App` with a
stub credential that is never actually asked for a token (a malformed JWT
fails LOCAL parsing before any credential is used, confirmed by hand) --
the test still exercises the real verifier, without touching ADC or the
network. Mutation-verified: reverting `verify_admin_token`'s exception
handling to swallow the verification failure turns this test red.

**The cleanup.** `scripts/purge_test_artifacts.py --project --dry-run`
lists exactly the enumerated shapes from the incident (alerts by firm_id
`{firm-a, acme}` or doc id `link_exhausted_jti-a`; `link_redemptions` and
`links` docs, bare and channel-suffixed, with a missing or `firm-a`
`firm_id`; `firms/firm-a` and every one of its subcollections, enumerated
dynamically via Firestore's own `collections()` call rather than a
hardcoded subcollection list) and writes nothing; `--apply` performs the
deletes. `--project` is required and pins the target deterministically
(same pattern as `scripts/bootstrap_firm.py`/`scripts/grant_credits.py`).
The maintainer runs `--apply` -- data deletion is theirs, per the bead.

## Lessons

A mock/fake proves the code CALLS the right seam; it says nothing about
whether that seam is REACHABLE for real on a machine with working
credentials (CLAUDE.md scar #7's neighbour, same family: a stub cannot tell
you the real dependency is live). Every existing store test in this repo
already patched ABOVE the real seam (`get_db()`/`_collection()`/`_get_db()`)
-- the guard never had to touch them -- but nothing PROVED that every test
did, until this bead's full-suite run under the guard proved it
mechanically by finding the one exception.

The two-target patch (not one) generalizes: when a real client is
constructed through a chain of lazy initialization (`initialize_app` ->
`get_app` -> `Client(...)`), guarding only the FIRST step in the chain
misses the case where an earlier, unguarded call already completed that
step. Guard the actual object that touches the network, not just its
caller.

## Doc freshness

`docs/standards/testing.md` bumped (2026-09-15): new "No real Firestore"
bullet describing the guard, why it exists, and the fix pattern for a test
it catches; `admin_backend/tests/conftest.py` added to the Tracks line.

## Files touched

- `backend/tests/conftest.py` -- autouse `_no_real_firestore` fixture.
- `admin_backend/tests/conftest.py` -- same fixture, imported from the
  shared module.
- `backend/tests/unit/_no_real_firestore.py` -- new: the shared guard
  implementation (`install_no_real_firestore_guard`,
  `RealFirestoreReachedInTest`).
- `backend/tests/unit/test_no_real_firestore_guard.py` -- new: pins the
  guard itself, mutation-verified per patch target.
- `admin_backend/tests/unit/test_access_matrix.py` -- fixed the one test
  the guard caught.
- `scripts/purge_test_artifacts.py` -- new: the cleanup CLI.
- `tests/test_purge_test_artifacts_cli.py` -- new: CLI contract tests
  against a hand-rolled fake Firestore.
- `docs/standards/testing.md` -- new bullet + Tracks line update.

Review outcomes recorded in the closeout ping.
