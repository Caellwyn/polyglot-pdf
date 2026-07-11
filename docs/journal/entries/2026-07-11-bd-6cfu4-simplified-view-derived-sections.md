---
date: 2026-07-11
bead: polyglot-pdf-6cfu.4
title: "Simplified view verified on derived-section kits: full f1040 + i-90 walkthroughs, manifest shape unchanged"
tags: [schema-editor, extractor, testing]
---

## Trigger

Sprint 10 (epic `polyglot-pdf-6cfu`): with divisions now derived
deterministically (6cfu.2) and the editor able to manage them (6cfu.3), bead
6cfu.4 verifies the SIMPLIFIED VIEW runs cleanly on derived-section kits
before the retrofit (6cfu.6) rewrites the shipped ones. Expected small: the
runtime reads `schema.sections` generically; this bead is the proof.

## What was verified (no product code changed)

Derived-section copies of f1040 (14 sections, printed-heading strategy) and
i-90 (28 sections, name-convention strategy) were generated with
`derive_sections.derive_and_apply` into a scratch store; the local stack
(vite + uvicorn on the scratch store, test-harness auth bypass) served them
to the real voice-app SPA.

- **f1040, full fill-and-advance walkthrough (14/14 sections):** every
  section navigated in order with fields filled; the required-field gate
  fired where expected ("Please complete all required fields") and cleared
  once satisfied; progress percentage advanced; the page-1 -> page-2
  boundary crossed cleanly; the balanced cap-split labels ("Dependents
  (1 of 2)" / "(2 of 2)") rendered; the PAGELESS "To review (unplaced)"
  section rendered as a normal final section holding the 4 positionless
  fields; "Submit Form" correctly replaced Next on the last section.
- **i-90:** sections 1-10 by fill-and-advance (sub-heading sections, the
  "Part 2. Application Type (continued)" label, radio groups, show_if
  reveals, pages 1-3); sections 11-28 via the voice-model's own switch path
  (`window.vffOnSectionChanged`) -- all 18 rendered their derived labels
  correctly (checked=18, allOk=true).
- **PDF view consistency (previewUi=1):** f1040 rendered both pages with 279
  field overlays on the same fill state; i-90 rendered all 7 pages with 166
  overlays. The PDF view is section-agnostic by design and unaffected.
- **Handshake manifest shape unchanged** on both derived kits:
  `buildHandshakeManifest` produced exactly the wire contract the backend
  consumes -- top keys `{current_section, previous_sections, parts}`,
  `current_section = {section_id, section_label, fields}`, `parts =
  [{id, order, label}]` (14 and 28 entries respectively).
- **Frontend vitest suite: 877 passed** (default forks pool, per the
  threads-pool scar), zero failures. Session-state persistence across
  reloads verified incidentally (walkthrough position survived the
  previewUi reload).

Exit criteria: (1) PASS -- both walkthroughs above, simplified + PDF views
consistent, navigation/validation/progress correct. (2) PASS -- manifest
shape verified on both kits; frontend suite green.

## Lessons

- The sandboxed preview CAN run the full voice-app SPA (its storage works
  there now; the app needed the test-harness bypass flags + the Firebase web
  config in `frontend/.env.local`, copied from `.env.demo`) -- but the HIDDEN
  tab gets INTENSIVE TIMER THROTTLING: `setTimeout`-based UI flows (the
  300ms `isNavigating` clear, in-page polling sleeps) stall for seconds to
  minutes. What looks like "Next button does nothing" is the throttled
  timer, not an app bug. Workaround: MessageChannel yields are NOT
  throttled -- use them instead of setTimeout for in-page waits, and
  click-retry loops for timer-gated buttons.
- `cp` with a backslash-style `C:\...` path inside double quotes in the Bash
  tool can silently write to a mangled destination -- the earlier schema
  swap "succeeded" without landing. Use forward-slash paths and `cp -v`.

## Doc freshness

- `.claude/launch.json` gained a `frontend` entry (vite :5173) so future
  sessions can preview-start the voice app directly. No tier-1/2 doc tracks
  it; freshness checker's STALE flags all track files this bead did not
  touch -- reviewed and left.

## Files touched

- `.claude/launch.json` (frontend dev-server entry)
- this journal entry
