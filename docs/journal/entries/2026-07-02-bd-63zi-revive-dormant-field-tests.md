---
date: 2026-07-02
bead: polyglot-pdf-63zi
title: "Revive the 3 dormant .NEEDS_CLEANUP field-component tests (31 tests back in the suite)"
tags: [testing]
---

## Trigger

Follow-up from the o0pc cleanup assessment: three field-component test files
(RadioField/SelectField/TextField) were parked for months via a
`.NEEDS_CLEANUP` rename that hides them from vitest's glob -- invisible
non-coverage. Bead polyglot-pdf-63zi: revive or delete-with-proof.

## What shipped

Renamed all three back and fixed them (a Sonnet subagent did the mechanical
fixing; orchestrator reviewed). Verdict: the tests were NEVER stale against
the components -- every original intent (incl. the FieldValue-unwrapping /
"[object Object]" regression tests) still matches the current component
contracts. The 27/31 failures were pure harness drift:

1. Missing explicit `afterEach(cleanup)` -- this repo sets no
   `test.globals`, so testing-library auto-cleanup never fires; DOM
   accumulated across tests making role queries multi-match. Every newer
   test file already follows the explicit-cleanup convention; these predated
   it.
2. `toBeInTheDocument()` -- `@testing-library/jest-dom` is not installed;
   the repo convention is `toBeTruthy()`.

Zero production-code edits; zero tests deleted; no component bugs found.
Full FE suite after revival: 34 files, 524/524 passing (up from 31 files /
470 before the section's tests returned + growth from dev).

docs/standards/testing.md: replaced the stale "Five are active / Five more
are dormant" claims (the other two parked files it named, schemaFormState +
connection, no longer exist on dev) with current state plus the two harness
conventions new component tests must follow; added a "do not park tests by
rename" rule.

Also rides this PR: the telemetry row for merged PR #291 (written after that
branch merged, so it had no branch of its own to ride).

## Lessons

- A test parked by renaming it off the glob is worse than a deleted test:
  it reads as coverage in the tree while asserting nothing, and it rots
  invisibly. The fix here took minutes once anyone looked; the parking
  lasted months. testing.md now bans the pattern.
- When a whole parked suite fails uniformly, suspect the harness before the
  subject: 27 failures had two root causes, neither in the components.

## Doc freshness

- Bumped + edited: docs/standards/testing.md (see above).
- No other doc tracks the three test files.

## Files touched

- frontend/src/schema-forms/components/fields/{TextField,RadioField,SelectField}.test.tsx
  -- renamed from *.NEEDS_CLEANUP + harness fixes (cleanup imports,
  toBeTruthy).
- docs/standards/testing.md -- current-state frontend suite description.
- docs/journal/telemetry/2026-07-03T00-28-11Z-0f62cf8a.json -- PR #291 row.
