---
date: 2026-09-17
bead: polyglot-pdf-wb1v4
title: "Bug-hunt batch 6: two stale comment fixes, an App.tsx enumeration reworded, three duplicate deploy-doc beads re-tiered"
tags: [testing, review]
---

## Trigger

Continuation of the open-ended bug-hunt mandate. `bd`/dolt were upgraded
mid-session (npm global reinstall, confirmed same-version but current) before
this batch started. Both `wb1v4` and `vzx0n` were filed by batch 5's own
outer cross-surface review; `ip43t` and the deploy-doc cluster were picked
from a broader survey of the ~386 ready sonnet/haiku-tier bug beads.

## What shipped

Three beads closed with real fixes:

- **`wb1v4`** -- `admin_backend/tests/unit/test_firm_routes.py:37`'s
  fake-Firestore comment still named `credit_ledger.read_entries()` as what
  `get_firm()` calls; it has called `read_recent_entries()` since bd
  `y1t68`. The same file's own line 597 mutation note already named the
  right function, so the file contradicted itself. Fixed the stale
  reference; verified the only remaining `read_entries` hit is the
  intentional mutation-note reference.
- **`vzx0n`** -- `backend/services/runtime_config.py`'s module docstring
  named `CREDITS_ENFORCED` the SOLE key with no env read, twice (lines
  ~50, ~64) -- `CREDIT_LOW_THRESHOLD` is a second one, per the same file's
  own `_legacy_env_default` docstring. Per CLAUDE.md scar #8, enumerated
  every count/enumeration claim in the docstring (5 total) before fixing:
  found exactly the 2 stale ones the bead named, the other 3 ("Five keys",
  "three legacy keys" x2) were already correct. Fixed both, verified the
  cited getter function names (`credits_enforced()`,
  `credit_low_threshold()`) actually exist before citing them.
- **`ip43t`** -- `admin-console/src/App.tsx`'s `refusedMidSession` comment
  enumerated 2 specific pages (`AuditLogPage`/`ConfigEditorPage`) as
  `onAuthExpired`'s callers; a third (`UsersPage`) was added by bd `z4y91`
  without updating the comment, and more pages have since adopted the same
  callback (8+ call sites today, still growing per Epic 2 Track C).
  Reworded to name the CONTRACT ("a call from any page fails with a 401 or
  403") instead of enumerating callers, per the bead's own suggested fix --
  so a new page needs no comment edit.

**Re-tiered, not fixed:** three beads (`q97d8`, `qwxy1`, `h6kct`) all
describe the SAME underlying problem -- `DEPLOYMENT.md`/`README.md` (and,
per `h6kct`, 11 total files) still documenting the local bash deploy engine
bd `oqtm7` deleted. Rewriting these accurately requires understanding the
new Cloud Build pipeline shape (cloudbuild.yaml's `frontend-resolve-urls`,
`backend-reachability-gate`, `firestore-rules` steps) across 7+ distinct
wrong claims, not a mechanical find-and-replace -- and `qwxy1` explicitly
raises a scope question ("should DEPLOYMENT.md even survive, or should it
be replaced by a pointer at the tier-2 docs") that is a product/scope call,
not mine to decide unilaterally. Re-tiered all three to `opus` and released
them, cross-referencing each other and recommending `h6kct` (the most
complete enumeration) as the consolidation target.

Fresh-eyes triage: no gaps found in self-review; no out-of-scope findings
beyond the three re-tiered beads.

## Lessons

- One pre-existing, timing-sensitive test flaked during this batch's full
  suite run: `backend/tests/unit/test_health.py::
  test_the_two_probes_have_independent_budgets` (asserts on a
  `time.sleep(1.0)` racing a monkeypatched `0.2s` timeout) failed once in a
  ~760s full-suite run under confirmed heavy concurrent-session load
  (20-23 python.exe processes observed throughout), then passed cleanly
  both standalone (twice) and is byte-identical to `origin/dev`. Diagnosed
  as environmental flakiness from a wall-clock-timing assertion under CPU
  contention, not a regression -- none of this batch's 3 fixes touch
  health probes, async scheduling, or timeouts. Per the "stash to prove
  pre-existing" pattern, confirmed via `git show origin/dev:...` rather
  than assuming.
- A near-duplicate cluster of doc beads (this session's fourth: after
  `admin-service.md`'s stamp chain in batch 4, and now the deleted
  bash-deploy-engine docs) keeps arising from multiple review passes
  independently flagging the same root cause at different times/scopes.
  Worth checking for siblings via a title/surface grep before claiming any
  docs-nit that names a recently-deleted/renamed mechanism.

## Doc freshness

No tier-1/2 docs touched this batch (all three fixes are code
comments/docstrings, not `docs/`). `check_doc_freshness.py` unaffected by
this batch's diff.

## Files touched

- `admin_backend/tests/unit/test_firm_routes.py` -- wb1v4 fix
- `backend/services/runtime_config.py` -- vzx0n fix
- `admin-console/src/App.tsx` -- ip43t fix
