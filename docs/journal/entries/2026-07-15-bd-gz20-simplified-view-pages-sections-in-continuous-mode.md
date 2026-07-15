---
date: 2026-07-15
bead: polyglot-pdf-gz20
title: "fix(frontend): simplified view does not page sections to follow the voice model in continuous mode"
tags: [hotfix, testing]
---

## Trigger

The maintainer reported that the voice app stopped changing sections visually in
the simplified view. After the move to a continuous backend feed (one Gemini
session for the whole form, no per-section resets -- bd polyglot-pdf-55jg), the
frontend needs to advance sections as the model's field focus advances, so the
shown section always contains the field being filled. It was not.

## What shipped

A frontend-only fix so the simplified view PAGES to follow the voice model in
continuous mode.

Root cause: in continuous mode the model fills fields across the whole form in one
session, but `SchemaForm` still renders one section at a time keyed on
`currentSectionId`, and `currentSectionId` stayed pinned to the first section
(section advancement is suppressed in continuous mode -- only manual prev/next was
ever wired to move it, and that is hidden in continuous mode). So when the model's
focus (`onNextField`) moved to a field in a later section, `handleNextField` called
`document.getElementById(fieldId).scrollIntoView()`, the element was not rendered
(wrong section shown), and the view was stranded on the first section.

The change:
- `SchemaForm.handleNextField` now, in continuous mode, resolves the section
  containing the focused field and pages the view to it BEFORE scrolling (the
  scroll is deferred two frames so the newly-mounted element exists).
- New `SchemaFormStateManager.findSectionIdForField(state, fieldId)` -- field ->
  section lookup, `[]`-alias aware (Gemini drops/adds the bracket).
- New `SchemaFormStateManager.setVisibleSection(state, sectionId)` -- pages the
  visible section following the model. It sets ONLY `currentSectionId`: it
  PRESERVES any `switch_to_field` pin (unlike the manual-jump `navigateToSection`,
  which clears the pin) and has no completed-section side effects. This
  distinction matters because `switch_to_field` sets the pin and THEN drives
  `onNextField`; since the connection's state and the component's state both persist
  through the same `sessionStorage` key, a pin-clearing save would clobber the pin
  that same tool just set.
- `handleNextField` reads current state via a new `stateRef` mirror, because the
  callback is captured once (the ConnectionManager is built in a `[streamReady]`
  effect) -- reading the closed-over `state` would see the mount-time values
  (continuous not-yet-enabled, first section).

Decisions (all mine, low-consequence, noted for audit):
- Added a SEPARATE `setVisibleSection` rather than a flag on `navigateToSection`,
  because the pin/completed-section semantics genuinely differ ("follow the model"
  vs "manual jump"). A parameter would have muddied two distinct intents.
- Format of the fix is frontend-only, matching the maintainer's scoping ("this
  would be a frontend issue").

Assess (Step 5.5.a rubric): all three exit criteria PASS -- (1) cross-section
paging pinned by a SchemaForm component test driving the real `onNextField`
callback; (2) pin-preservation + no completed-section growth pinned by state-manager
tests; (3) no auto-paging outside continuous mode pinned by a test, full suite +
typecheck green.

Fresh-eyes (Step 5.5.b): <FILL: rounds + adopt/reject/defer>.
Outer review (Step 5.6): <FILL: rounds + two-independent NO-GAPS>.

Verification: 992 frontend tests green (11 new: 4 for `findSectionIdForField`, 4
for `setVisibleSection` incl. pin-preservation vs `navigateToSection`, 3 SchemaForm
component tests driving the captured `onNextField`); tsc clean; full backend suite
(1082 passed) green via closeout prep. Live-verified in Chrome on the I-90 (27
sections): with continuous mode on, the simplified view paged Section 1 -> Section 3
following the focused field, Next/Prev suppressed (continuous mode), and the running
bundle was confirmed to contain the new symbols + wiring. A true voice-driven
end-to-end (Gemini actually advancing fields) was NOT run -- the local runner is
AI-Studio-only and those credits are depleted; that path is Vertex/voice-harness
territory. Maintainer accepted local verification as sufficient.

## Lessons

Two frontend-specific traps, both narrow enough to keep in this entry rather than a
standards doc:
- A callback captured once by a `[dep]`-scoped effect (here the ConnectionManager's
  `onNextField`) sees stale closure state; mirror current state into a ref (the
  existing `isMobileRef`/`connectionManagerRef` pattern in this file) instead of
  reading the closed-over value.
- Two `SchemaFormState` holders (the connection and the component) persist through
  the same `sessionStorage` key, so a state mutation on one can clobber a field the
  other just wrote. A "follow the model" section-page must therefore preserve the
  `switch_to_field` pin -- hence `setVisibleSection` is pin-preserving, distinct
  from the manual-jump `navigateToSection`.

## Doc freshness

Bumped `docs/components/schema-forms.md` (its `**Tracks:**` covers the two changed
frontend files) to today, describing that `currentSectionId` now FOLLOWS the voice
model via `setVisibleSection` (it was documented as "inert / pinned to the first
section"). closeout prep flagged many other STALE docs, but every one of them tracks
backend files this branch did NOT touch (they were stale before this branch, from
other sprints' 07-12..07-15 backend work) -- left as-is per the doc-freshness rule.

## Files touched

- `frontend/src/schema-forms/components/SchemaForm.tsx` -- `handleNextField` pages
  the view in continuous mode; added `stateRef` mirror.
- `frontend/src/schema-forms/state/schemaFormState.ts` -- new `findSectionIdForField`
  + `setVisibleSection` (pin-preserving).
- `frontend/src/schema-forms/components/SchemaForm.test.tsx` -- 3 continuous-mode
  paging tests driving the captured `onNextField`; capture the 5th ctor arg.
- `frontend/src/schema-forms/state/schemaFormState.test.ts` -- tests for
  `findSectionIdForField` + `setVisibleSection`.
- `docs/components/schema-forms.md` -- current-state prose + date bump.
