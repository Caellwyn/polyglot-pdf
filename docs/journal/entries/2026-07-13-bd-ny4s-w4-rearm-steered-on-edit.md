---
date: 2026-07-13
bead: polyglot-pdf-ny4s
title: "W4: re-arm steered markers on value change (correction re-validates)"
sprint: 12
tags: [refactor, testing]
---

## Trigger

Sprint-12 epic 09da (decoupled async validator), child W4 -- a lifecycle fix the
maintainer flagged reviewing PR #413 (2026-07-12). A field's `steered` marker (the
per-field "the validator already flagged this once" flag that enforces the
max-resteer bound) set at steer delivery and NEVER cleared: `updateField` carried
it forward unconditionally. Consequence: a user CORRECTION to an adjudicated field
was never re-validated (a correction that introduces a fresh contradiction slipped
the net), and a genuinely new conflict on a steered field was suppressed forever.

## What shipped

RE-ARM the marker on a VALUE change, in the `updateField` write path
(schemaFormState.ts). The unconditional carry-forward becomes conditional: carry
`steered` forward ONLY when the field's normalized value did not change; a value
change CLEARS it, so the corrected field re-enters the validator net.

- New private `_sameFieldValue(a, b)` helper: value-equality for the re-arm
  decision. Handles primitives (===), checkbox-group arrays as SETS (order-
  insensitive, blanks dropped -- see the fresh-eyes fix below), and treats all
  empty-ish values (undefined / null / '' / all-blank []) as "no value" so a
  clear-to-blank of a previously-filled field counts as a change.
- `updateField` now computes the normalized incoming value up front, compares it to
  the alias-safe prior value, and only carries the marker when unchanged. An
  incoming FieldValue with an EXPLICIT `steered` still wins (the caller asserted
  intent); re-arm only governs the implicit carry-forward.

**The no-nagging guarantee (jnjj.17 criterion 3) is preserved where it matters.** A
user who confirms "both are intentional" changes NO value, so the marker stays and
they are never re-asked; only a field whose value actually moved re-arms. The
validatorsteer E2E test (confirm -> steer -> re-confirm-without-change) still
passes, pinning this.

**Decision (autonomous, defended):** re-arm keys on the NORMALIZED value (both the
prior stored value and the incoming value pass through `normalizeFieldValue`), not
the raw input -- otherwise a cosmetic re-format of the same answer (e.g. an
A-Number's separators) would spuriously re-arm. Comparing normalized values makes
"the answer actually changed" the trigger, matching the intent.

**Fresh-eyes fixes (Sonnet) -- two REAL no-nagging violations, both adopted.**
(1) The array comparison was ORDER-SENSITIVE, but the real
`CheckboxField.handleToggle` APPENDS a re-checked value, so the same checkbox set
re-written as `['b','a']` instead of `['a','b']` read as a change -> spurious
re-arm (nagging on a no-op toggle). Fixed: a checkbox group is a SET, so the
comparison is now order-INSENSITIVE (sorted, blanks dropped). (2) The schema-field
lookup for normalization was exact-key-only, so a value written under the
bracket-variant of a `format_preset` field (a_number) was stored UN-normalized; a
later same-answer canonical write normalized and compared unequal -> spurious
re-arm. Fixed: the field lookup is now alias-aware (mirrors the prior-entry
fallback) AND the prior value is normalized before comparison, so both sides are
canonical. Both pinned by new regression tests. (One of my initial regression
tests was itself wrong -- it unchecked a box then re-checked it in two steps, and
the intermediate shrunk-set state is a LEGITIMATE change; corrected to a
single-write same-set-reordered case, which is the actual bug.)

## Lessons

The four pre-W4 "PRESERVES the steered marker across a manual edit" tests all
edited to a DIFFERENT value and asserted preservation -- they encoded the exact
bug this bead fixes (unconditional carry-forward). Updating them to the new
contract (value-change -> clear; unchanged -> keep), plus splitting the
alias-migration tests into a same-value (preserve) and a changed-value (re-arm)
case, is the substance of proving the behavior flipped correctly. A test that
asserts the buggy invariant will "pass" right up until the fix -- reading WHY each
failing test failed (it edited the value) is what distinguishes "my change broke it"
from "my change correctly inverted it."

## Doc freshness

- **Bumped** docs/standards/validation-delegation.md: the `steered` contract-2 note
  now records that the marker is NOT session-permanent -- it re-arms on a value
  change (the bead explicitly asked to note this if the doc implied permanence, and
  it did: "already steered back ... once" with no clear path).
- Disjoint from W2/W3 (this touches only the `updateField` write path); no other doc
  invalidated.

## Files touched

- frontend/src/schema-forms/state/schemaFormState.ts -- `_sameFieldValue` helper +
  re-arm logic in `updateField`.
- frontend/src/schema-forms/state/schemaFormState.test.ts -- updated the 4 pre-W4
  preservation tests to the re-arm contract (value-change clears; added
  unchanged-keeps + explicit-steered-wins cases).
- frontend/src/schema-forms/state/schemaFormState.rearm.test.ts (new) -- re-arm
  integration (text/checkbox/clear-to-blank/re-mark) + the `_sameFieldValue` helper.
- docs/standards/validation-delegation.md -- steered re-arm note + bump.
