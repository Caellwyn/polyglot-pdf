---
date: 2026-06-13
beads: [polyglot-pdf-r2hy, polyglot-pdf-nzuy, polyglot-pdf-icjr]
pr: TBD
tags: [refactor, testing]
---

# Bundle: confirm-spin session cap (r2hy) + supplement dedup (nzuy) + telemetry pointer (icjr)

Three small fixes bundled into one PR, all outside the Gemini-API / reconnection /
test-coverage surfaces another session is working (maintainer constraint this
sprint).

## Trigger

A second "grab some more small beads and bundle" pass after PR #184 merged.
Constraint: avoid the Gemini Live API, test-coverage, and reconnection areas
(other sessions own those; specifically the jf6w connection-timeout-modal epic and
the l3a Live-API-session-management epic).

## What shipped

### r2hy -- session-wide cap on the 0y7 unconfirmable-confirm loop-breaker

The 0y7 loop-breaker in `webFormConnection.handleConfirmFieldRequest` re-prompts
Gemini when it tries to `confirm_field` a field with no usable value, capped
per-field (a streak counter keyed on `lastUnconfirmableFieldId`). But the per-field
counter resets whenever a DIFFERENT field is confirmed, so a model spinning across
fields in pairs (A,A -> B,B -> A,A ...) re-armed the per-field re-prompt on every
switch and could re-prompt without bound. This is the exact gap Codex flagged (and
wpw.3 closed) for the validation-reject breaker.

Fix: add `unconfirmableSessionPromptCount` + `UNCONFIRMABLE_SESSION_CAP = 6`,
mirroring `VALIDATION_REJECT_SESSION_CAP`. The session counter is NOT reset on a
field change -- only on (re)connect, section switch, or a successful confirm of the
*stuck* field (genuine progress restores the budget; an unrelated success does not,
or [empty-A, good-B] alternation would reset it forever -- the wpw.3
fresh-eyes-round-4 lesson). Introduced a `resetUnconfirmableTracking()` helper and
replaced the 4 inline 3-line reset blocks (connect, backend-section-switch,
startSection, switchToSection) with it -- both fixing the bug and removing the
duplication that let the session counter be forgotten at a reset site.

Tests: two new cross-field tests in `webFormConnection.confirmloop.test.ts` -- one
asserts the total re-prompts under a paired-spin (A,A,B,B,...) are bounded by the
session cap (<=6, not ~50); one asserts a successful confirm of the stuck field
restores the budget so a later field can earn re-prompts again. Note recorded in
the test: pure strict alternation (A,B,A,B) never prompts at all, because the
per-field LIMIT=2 gate needs two CONSECUTIVE same-field confirms -- the unbounded
case is paired spin, which is what the test drives.

### nzuy -- dedup supplements in the chunked-bakeoff merge

`scripts/bakeoff/arm_llm_native_chunked.py` `_merge()` deduped parts and sections
by id (first-seen wins) but appended supplements unconditionally, so multiple
page-chunks each emitting the same supplement produced duplicate entries in the
merged output (mildly wrong scored structure). Fix: dedup supplements by id (name
fallback), first-seen wins, matching the parts/sections pattern. Research/throwaway
script, no test; verified by `ast.parse` and reading the function.

### icjr -- discoverable telemetry-dataset pointer

Harness telemetry is split: `docs/journal/harness_ledger.jsonl` is the
pre-2026-06-10 archive, and `docs/journal/telemetry/*.json` (97+ files) is the
current per-closeout system. Reading only the JSONL made it look like telemetry
stopped on 06-10 -- which actually misled an analysis during an h2r.4 review. Added
a `docs/journal/telemetry/README.md` (the two sources, how to combine them: dedup
by `session_id` + `recorded_at`) and a pointer line in `docs/journal/README.md`.

## Lessons

A loop-breaker keyed only per-field is not a session bound: any state that resets
on a field change can be defeated by cross-field alternation. When adding a
per-field rate limit, add the session-wide companion in the same change (the
wpw.3 -> r2hy repeat shows the per-field-only version is the easy default to reach
for and the easy gap to leave). Generalizable -- noted alongside the existing
two-layer pattern in the code comment.

Also: a "blocked by another branch" bead can unblock mid-session. `nzuy` targeted a
file (`arm_llm_native_chunked.py`) that was only on the `research/7a9.11`
branch at claim time; I released it. When that branch merged to dev (PR #185)
mid-session, the file landed on dev and the fix became safe on a dev-based branch,
so I re-claimed and folded it in.

## Doc freshness

`docs/journal/README.md` and the new `docs/journal/telemetry/README.md` are the
icjr deliverable (not freshness bumps). No tier-1/tier-2 component/standard doc
tracks `webFormConnection.ts`'s confirm-loop logic or the bakeoff script
specifically; the doc-freshness gate result is recorded at closeout.

## Files touched

- `frontend/src/webFormConnection.ts` -- session cap + resetUnconfirmableTracking helper (r2hy)
- `frontend/src/webFormConnection.confirmloop.test.ts` -- 2 cross-field regression tests (r2hy)
- `scripts/bakeoff/arm_llm_native_chunked.py` -- supplement dedup in _merge() (nzuy)
- `docs/journal/telemetry/README.md` (new) + `docs/journal/README.md` -- telemetry pointer (icjr)
