---
date: 2026-09-15
bead: polyglot-pdf-2k2os
title: "bug hunt batch 2: admin alert sort order, jti guard, lazy import, unbounded ledger read, PII guard blind spot"
tags: [testing, review, security]
---

## Trigger

Self-directed sonnet/haiku bug-hunt sweep (second batch), following on from the
first batch closed in PR #800. The maintainer's instruction: self-select simple
beads tagged `tier: sonnet` / `tier: haiku`, fix and close as many as possible,
re-tier to `opus` and release any that prove more complex on investigation
(touching multiple surfaces or a real design call).

## What shipped

Five small, independently-scoped fixes, each with its own pinning test,
mutation-verified by reverting the fix and confirming the new test goes red:

- **`admin_backend/routes/alert_routes.py`** (bd polyglot-pdf-xq3nb): both
  alert-list routes' sort keys put a row with a missing `ts` FIRST instead of
  LAST. The sort key was `(r[1].get("ts") is None, r[1].get("ts"))` under
  `reverse=True` -- `reverse` flips the `is None` boolean too, so a missing-ts
  row (`True`) sorted before a present one (`False`) once reversed, the exact
  opposite of the intent. Fixed to sort on "has a ts" instead
  (`r[1].get("ts") is not None, r[1].get("ts") or 0`), which is invariant
  under the reverse flip.
- **`backend/services/alerts.py`** (bd polyglot-pdf-6fs96): `record_link_exhausted`
  had no `jti` guard, unlike its sibling mirror write on the same teardown
  path. A `None`/empty/non-string `jti` would write a stray
  `link_exhausted_<garbage>` document. Added the same guard the sibling
  already had.
- **`admin_backend/routes/audit_routes.py`** (bd polyglot-pdf-8uraj): a
  `google.api_core.exceptions` import sat at module scope, unlike every other
  `google.*` import in this router package, which are all lazy (inside the
  function). A module-scope import here would take down all 13 routers on an
  `ImportError` instead of just this one route. Moved it into the function
  body to match convention.
- **`backend/services/credit_ledger.py` + `admin_backend/routes/firm_routes.py`**
  (bd polyglot-pdf-2k2os): `GET /admin/firms/{id}` read a firm's **entire**
  ledger subcollection (no cap, no TTL/pruning) just to serve a 50-row page,
  via `read_entries(limit=None)` followed by a Python-side reverse and slice.
  Added `read_recent_entries()`, a newest-first Firestore query bounded to
  `limit + 1` documents (the "limit+1 trick" already used in
  `audit_routes.py`, computing a truncation flag with no second round trip),
  and switched the route to it. This is the most consequential fix in the
  batch: unbounded cost on the console's most-visited page for an active firm.
- **`backend/tests/test_no_pii_logging.py`** (bd polyglot-pdf-2k2os, same
  bead as the ledger fix -- bundled): the PII-sweep guard's `_LOG_CALL_START`
  regex only matched `_log.*(...)` call shapes. It was blind to
  `get_structured_logger().log_text_ai_usage(/log_tts_usage(/
  log_gemini_api_response(` -- three usage-event emitters that carry the
  same kind of sensitive kwargs the guard exists to catch, invisible to the
  static scan purely because of the call shape, not the file set. Widened
  the pattern to cover all three. No live leak was found (verified by
  reading each call site) -- this closes a blind spot in the guard itself,
  not a leak it missed.

Also closed without a code change (verified stale against current code before
touching anything):
- **polyglot-pdf-nw9np**: cited an implicit-`Optional` type annotation that
  no longer exists in the current code.
- **polyglot-pdf-y1t68**: `cloudbuild.yaml` already invokes
  `npm run test:run`, not the bare `npm test` the bead described.

One bead was investigated and **re-tiered, not fixed**:
- **polyglot-pdf-cmwj2** (sonnet -> opus, released unclaimed): its own exit
  criteria require enumerating every `.error(..., reason=str(exc))` /
  `.error(..., error=str(e))` site across `backend/` per CLAUDE.md scar #8
  ("enumerate the set before fixing any of it"). A grep found ~90 such sites,
  not the one or two a sonnet-tier fix assumes. Even the bead's own
  lighter "enumeration test only" fallback still requires a real design
  decision (what shape the pinning test takes for a 90-site set) better made
  at a higher tier than force-fixed or narrowly shortcut here.

Fresh-eyes (Sonnet, diff-size routed) and the outer Opus cross-surface review
both ran on the local diff pre-PR and cleared `NO-GAPS` in one round each; no
findings needed triage.

Full local suite, run from the worktree pre-PR: 6059 backend/root tests passed
(287 skipped, 3 deselected, exit 0); 2326 frontend vitest tests passed (162
files); 148 admin-console vitest tests passed (14 files, retried once after an
initial `--pool=threads` timeout caused by three heavy suites running
concurrently and starving the thread-pool startup -- not a real failure, the
suite passed cleanly alone once the backend suite finished).

## Lessons

- A `reverse=True` on a sort key tuple flips **every** field in the tuple,
  including a boolean built from `is None` -- if the intent is "always sort
  missing-value rows last regardless of direction," key on the positive
  condition ("has a value"), never the negative one, so the reverse flip
  can't invert the missing-value placement.
- A PII/PHI static guard's coverage is defined by its call-shape regex, not
  just its file list (`GUARDED_FILES` / the deny-by-default sweep). Adding a
  new emitter method on an existing logger object (`get_structured_logger()`
  gaining `log_tts_usage` alongside `log_gemini_api_response`) is invisible
  to a guard written against the OLD method names unless the pattern is
  widened generically or per-method. Worth checking whenever
  `structured_logger.py` grows a new public method.

## Doc freshness

`docs/standards/hipaa-pii-policy.md` was flagged STALE by
`check_doc_freshness.py` against this branch's change to
`backend/tests/test_no_pii_logging.py`. Its blind-spot paragraph explicitly
claimed the guard detects "only two shapes" (kwargs in `_log.*()` calls +
`print()` f-strings) -- no longer accurate once `_LOG_CALL_START` also
matches the three `get_structured_logger()` usage-event methods. Updated the
prose to name the third shape and bumped the stamp (separate commit,
`a8d3f46b`).

All other STALE docs `check_doc_freshness.py` flagged (auth.md,
config-deployment.md, context-compression.md, jit-schema.md, pdf-filling.md,
schema-forms.md, tool-call-flow.md, voice-ai.md, websocket-routing.md,
ai-models.md, bead-tiers.md, logging-and-cost.md, risk-rating.md,
schema-key-visibility.md, section-reset-deprecation.md, si-reduction.md,
stateless-architecture.md, terminology.md, testing.md,
validation-delegation.md, voice-and-vad.md, ws-protocol.md,
technical_guide.md) track files this branch did not touch -- pre-existing
staleness from other concurrent work on `dev`, left as-is per the closeout
rule (only bump a doc whose tracked files THIS branch changed).

## Files touched

- `admin_backend/routes/alert_routes.py` -- fix both alert-list sort keys
- `admin_backend/routes/audit_routes.py` -- move `google.api_core` import to lazy/function-scope
- `admin_backend/routes/firm_routes.py` -- use `read_recent_entries()` instead of `read_entries(limit=None)`
- `admin_backend/tests/unit/test_alert_routes.py` -- pinning tests for both sort fixes
- `admin_backend/tests/unit/test_firm_routes.py` -- pinning test for the bounded ledger read
- `backend/services/alerts.py` -- jti guard on `record_link_exhausted`
- `backend/services/credit_ledger.py` -- new `read_recent_entries()` function
- `backend/tests/test_no_pii_logging.py` -- widen `_LOG_CALL_START` to cover the three usage-event methods
- `backend/tests/unit/test_alerts_dedup.py` -- pinning test for the jti guard
- `frontend/src/console/consoleStyles.test.ts` -- corrected a false docstring claim about FirmAlertsBanner.tsx
- `docs/standards/hipaa-pii-policy.md` -- updated blind-spot prose, bumped stamp
