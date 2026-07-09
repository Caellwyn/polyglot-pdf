---
date: 2026-07-08
bead: polyglot-pdf-ipin polyglot-pdf-jq17 polyglot-pdf-fdz8
title: "Preview-mode polish: live-resize view fallback, single-option checkbox X, overlay-invariant test"
sprint: 8
tags: [conventions, testing, gotcha]
---

## Trigger

Three small deferred beads left open after the preview-mode epic
(`polyglot-pdf-js7q`) closed, bundled into one cleanup PR. All three touch the
`frontend/src/pdf-view/` surface (`docs/components/pdf-view.md`).

## What shipped

- **ipin -- live-resize view fallback.** The Simplified/Preview mode was chosen
  once at mount (`initialViewMode`) and never re-evaluated against width, so a
  user in Preview on a wide window who resized the SAME tab down to mobile (or
  rotated a device) stayed in Preview -- the mobile-defaults-Simplified intent
  (epic rubric #5) held only for a fresh mount. Added a pure
  `viewModeAfterResize(current, viewportWidth)` helper in `viewMode.ts` and
  wired it into SchemaForm's existing debounced resize effect: crossing INTO
  mobile width (`<= MOBILE_INITIAL_BREAKPOINT`, 768) forces Preview back to
  Simplified. One-directional on purpose -- growing back to desktop does NOT
  auto-restore Preview, and a desktop-width resize keeps the current mode, so a
  deliberate desktop choice is never overridden.

- **jq17 -- single-option checkbox paints an X, not a label.** `valuePainting.ts`
  routed ANY options-bearing `checkbox` (even a 1-element options array) to
  `paintSelectedLabels`, which paints the option LABEL text inside the
  field-level rect. Since `CheckboxField` renders any options-bearing checkbox
  as a multi-box group and stores the checked state as a 1-element array (e.g.
  `['c1_2[0]']`), a single-option checkbox would paint its label overflowing an
  ~8x8pt box instead of a check. Fixed: `options.length <= 1` now paints an X
  (new `isCheckboxChecked` helper handles both the boolean and the
  1-element-array forms); only a TRUE multi-option group (2+ options /
  `checkbox_group`) still paints joined labels.

- **fdz8 -- overlay-outside-view-switch invariant test.** New
  `frontend/src/schema-forms/components/SchemaForm.test.tsx` (jsdom, heavy
  children mocked) pins two things: (1) the Simplified/Preview toggle renders
  only with the preview flag on; (2) the voice overlay's DOM node survives a
  Simplified->Preview toggle as the SAME element -- a future refactor nesting
  the overlay inside the `viewMode` ternary would remount it (resetting the
  Gemini session) and this identity check goes red. It also carries the ipin
  live-resize assertion. Both mutation checks were verified by temporarily
  breaking the code (a `key={viewMode}` on the overlay reddens the identity
  test; gating the resize reset off reddens the ipin test).

## Scar tissue / gotcha

**jq17's concrete repro cases were dissolved by the schema-v2 flip, so its exit
criterion was adapted.** The bead (filed 2026-07-06) named `f1040`'s
`fld_combat_zone` and `w7`'s `reason_a` as single-OPTION checkboxes with a
1-element `options` array. Two days later the schema-v2 strictness flip (PR #346,
2026-07-08) migrated those kits: v2 now **forbids a `checkbox` with options**
outright (`backend/models/form_models.py`: "a v2 checkbox is a standalone
boolean; options are forbidden -- model the group as type=checkbox_group"), and
v2 is the only accepted shape. In the current corpus ALL 69 `checkbox` fields
have `options: null`; the only options-bearing checkboxes are 3 genuine
`checkbox_group` fields. So the jq17 bug is no longer reachable through any
shipped schema -- but the fix is still a correct hardening of the form-kit-
generic `valuePainting.ts` for hand-authored / pre-v2 kits. The unit test
therefore uses a SYNTHESIZED single-option shape (the combat-zone field's real
pdf value `c1_2[0]`, given a 1-element options array) rather than reading it
from the live schema.json, since the live schema no longer carries that shape.
Documented in the bead and defended in the PR.
