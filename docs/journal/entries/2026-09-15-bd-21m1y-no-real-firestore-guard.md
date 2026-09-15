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

**Round 2 (cross-surface review gap fix).** The Opus cross-surface review
found the two-target patch above was not actually sufficient: firebase_admin
caches clients on the App object (`_FirestoreService._clients`) for the life
of the process, so once ANYTHING in a process -- including
`backend/services/auth.py`'s own import-time `initialize_app()` plus one
real `get_db()` call -- has warmed that cache, every LATER call to
`firebase_admin.firestore.client()` is a cache HIT that returns the cached
real client without ever reaching the `google.cloud.firestore.Client`
constructor the guard patched. The reviewer reproduced this three ways,
including in-situ against this repo's own guard function, with no
`@external` marker involved. Fixed by adding a THIRD patch target,
`firebase_admin.firestore.client` itself -- the one function every consumer
in this repo actually calls, sitting ahead of both the App-service cache
lookup and the `_clients` dict lookup inside it, so a cache hit is caught
exactly as reliably as a cache miss. Added
`test_get_db_is_still_caught_when_the_client_is_already_cached`, which
manufactures a warm `_FirestoreService` cache directly and proves `get_db()`
still raises; mutation-verified by removing the new patch line and watching
that test (and only that test) go red. Full three-root suite reconfirmed
green after the fix: `backend/tests` 3753 passed / 195 skipped / 4
deselected, `admin_backend/tests` 585 passed, root `tests/` 1664 passed / 92
skipped.

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

Round 2 sharpened this further: a CACHE inside that chain is its own,
separate hole from the initialization-order hole above. Patching the
constructor a chain ends in is not the same as patching the FUNCTION that
chain is entered through -- a cache sitting between the two means the
constructor can go permanently unreached after the first real call, while
the entry-point function is called by every single consumer, cache hit or
miss, every time. When a guard patches "the thing that eventually touches
the network," check for a cache between the public entry point and that
thing; if one exists, the entry point itself is the seam to patch.

Adopt/reject/defer breakdown for round 2's reviewer findings:
- **Adopted (blocker, fixed then):** finding 1, the warm-cache bypass of the
  Firestore guard -- third patch target added, new mutation-verified test.
- **Deferred then (nit, filed as its own bead by the reviewer):**
  finding 2 (`polyglot-pdf-bpzsr`, purge script's stale test-name comment),
  finding 3 (`polyglot-pdf-zqwem`, the third `tests/` testpath has no
  Firestore guard of its own), finding 4 (`polyglot-pdf-5qbjd`, the purge
  script cannot reach `kits/{kit_id}/usage` rollups). None reopened or
  refuted then; verified all three beads exist with accurate bodies matching
  the review report.
- **Rejected then:** none -- every classified finding was either fixed or
  was already correctly filed rather than needing rebuttal.

Adopt/reject/defer breakdown for round 3's reviewer findings (a fresh-eyes
pass that independently re-raised two of round 2's already-filed nits,
without visibility into the beads tracker):
- **Adopted (fixed here):** the reviewer's two GAPS-FOUND findings, which
  turned out to be the same two gaps as `polyglot-pdf-bpzsr` and half of
  `polyglot-pdf-zqwem`:
  - `admin_backend/tests/conftest.py`'s docstring wrongly claimed
    `tests/conftest.py` "carries this same guard" -- corrected to state
    accurately that `tests/` has the K_SERVICE-strip guard but NOT
    `_no_real_firestore`, and why (no Firestore-store-exercising tests
    under `tests/` today). This is the docstring-accuracy half of
    `polyglot-pdf-zqwem`; that bead's actual exit criteria (installing the
    guard in `tests/conftest.py` itself) remain open and unaddressed --
    noted on the bead, left open.
  - `scripts/purge_test_artifacts.py`'s comment claimed a
    `test_*_matches_service_constants` pin that did not exist -- added
    `test_collection_constants_match_service_constants` (pins the four
    collection literals against `alerts.py`/`link_redemptions.py`/
    `links_store.py`/`firms.py`'s real constants, importing those four leaf
    modules directly since none of them imports `backend.services.auth` at
    module scope) and `test_known_channels_matches_every_admin_route_copy`
    (pins `KNOWN_CHANNELS` against all three `admin_backend/routes/*.py`
    copies via source-text regex, avoiding an import of those route modules
    which would transitively trip `backend.services.auth`'s import-time
    `initialize_app()`); updated the comment to name the real tests. Both
    mutation-verified (break each constant, watch the matching test go red,
    restore). This fully met `polyglot-pdf-bpzsr`'s exit criteria, so that
    bead is CLOSED (with the mutation evidence on the bead itself) rather
    than left as a stale duplicate.
  - Full three-root suite reconfirmed green after both fixes:
    `backend/tests` 3753 passed / 195 skipped / 4 deselected,
    `admin_backend/tests` 585 passed, root `tests/` 1666 passed / 92
    skipped.
- **Deferred (unchanged, not this round's scope):** `polyglot-pdf-zqwem`'s
  remaining exit criteria (actually installing the guard in
  `tests/conftest.py`) and `polyglot-pdf-5qbjd` (kit-rollup purge gap) --
  neither raised again by round 3's reviewer, both correctly out of scope
  for a docstring/comment-accuracy fix.
- **Rejected:** none.

## Doc freshness

`docs/standards/testing.md` bumped (2026-09-15): new "No real Firestore"
bullet describing the guard, why it exists, and the fix pattern for a test
it catches; `admin_backend/tests/conftest.py` added to the Tracks line.

## Files touched

- `backend/tests/conftest.py` -- autouse `_no_real_firestore` fixture.
- `admin_backend/tests/conftest.py` -- same fixture, imported from the
  shared module.
- `backend/tests/unit/_no_real_firestore.py` -- the shared guard
  implementation (`install_no_real_firestore_guard`,
  `RealFirestoreReachedInTest`); round 2 added the third patch target
  (`firebase_admin.firestore.client`) closing the warm-cache gap.
- `backend/tests/unit/test_no_real_firestore_guard.py` -- pins the guard
  itself, mutation-verified per patch target; round 2 added
  `test_get_db_is_still_caught_when_the_client_is_already_cached`.
- `admin_backend/tests/unit/test_access_matrix.py` -- fixed the one test
  the guard caught.
- `scripts/purge_test_artifacts.py` -- new: the cleanup CLI; round 3
  corrected a comment falsely claiming a CI pin that did not yet exist.
- `tests/test_purge_test_artifacts_cli.py` -- new: CLI contract tests
  against a hand-rolled fake Firestore; round 3 added
  `test_collection_constants_match_service_constants` and
  `test_known_channels_matches_every_admin_route_copy`, making that
  comment's claim true.
- `docs/standards/testing.md` -- new bullet + Tracks line update.

Review outcomes recorded in the closeout ping.
