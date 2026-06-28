---
date: 2026-06-28
bead: polyglot-pdf-vq4m
title: "fix(schema-forms): show_if equals operator never matches a checkbox-group trigger"
tags: [testing]
---

## Trigger

bd polyglot-pdf-vq4m, found during the PR #253 (bd wf3q) fresh-eyes review of the
G1b clean-corpus answer key. The answer-key author noticed that the I-90's
`p5_line1b_language` (interpreter language) is `show_if equals P5_Checkbox1b[0]`
on the `p5_checkbox1a` checkbox GROUP -- and that this dependent never becomes
visible in the production renderer regardless of selection. Root cause:
`shouldShowField`'s `equals` operator did a strict scalar compare against a value
that, for a checkbox group, is a `string[]`.

Picked up immediately after merging the editor group/ungroup feature (s4dp.1),
which is directly adjacent: that feature EMITS `equals <option value>` show_if
conditions on consolidated radios, so this operator has to handle the cases the
editor produces.

## What shipped

A one-spot fix in `frontend/src/schema-forms/utils/validation.ts#shouldShowField`,
plus the first tests for that function.

- **The bug:** a multi-option `CheckboxField` emits a `string[]` of selected
  option values. `shouldShowField`'s `equals` branch did `triggerValue === value`,
  so `["P5_Checkbox1b[0]"] === "P5_Checkbox1b[0]"` is always `false` -- the gated
  dependent never shows. On the I-90 this left FIVE fields unreachable in the
  production renderer: `p5_line1b_language`, `p5_line2_nameofrepresentative`, and
  `p4_line1a/1b/1c_accomodationrequested`, all `equals`-gated on a checkbox-group
  trigger.
- **The fix:** for an array trigger, `equals` now means MEMBERSHIP -- the selected
  set includes `value` -- via `triggerValue.includes(String(value))`, matching the
  `String()` coercion convention the `contains`/`in` branches already use.
  `not_equals` got the symmetric fix (a strict `array !== string` is always true,
  which would always-SHOW the dependent). Scalar (radio/select/text) triggers keep
  strict `===`/`!==`.
- **Tests:** added the first-ever `shouldShowField` tests (there were ZERO) -- the
  exact I-90 `p5_checkbox1a` scenario (selected option shows the dependent, a
  different option / empty group hides it, the option among several selected shows
  it), the scalar path, and the `not_equals` inverse. Full frontend suite green
  (25 files, 409 tests); `tsc --noEmit` clean.

**Exit-criteria scorecard:** crit 1 (a checkbox-group trigger selecting the gated
option makes its `equals`-gated dependent visible; an unselected option leaves it
hidden; verified by a validation.test.ts case) -- PASS, via the new
`shouldShowField (checkbox-group equals/not_equals trigger)` describe block.

**Fresh-eyes assess (Sonnet, pre-PR):** NO-GAPS, round 1.

**Codex review (PR #259) caught an incomplete fix.** A checkbox-group value has
TWO representations in this system, and the first fix only handled one:
- the interactive `CheckboxField` renderer emits a `string[]` (handled);
- the **voice-AI fill path** stores a COMMA-SEPARATED STRING
  (`"P5_Checkbox1b[0], P5_Checkbox2[0]"`) -- `backend/config.py:447` instructs
  Gemini to send comma-separated exact values, `validateOptionMembership` already
  splits on `,` for the group, but `SchemaFormStateManager` stores the raw string
  un-split. For that shape `triggerValue` is a STRING, not an array, so it fell
  through to strict `===` and the AI path stayed broken for multi-selects.

Fixed by resolving the trigger into a "selected set" before comparing: array as-is,
comma-string split (mirroring `validateOptionMembership`'s parsing), plain scalar
-> null (keeps strict identity). `equals`/`not_equals` check membership against
that set. Added 4 tests for the comma-separated AI path (multi-select present/
absent, single comma-free string, not_equals). Full frontend suite green (413).

**Decisions (mine):**
- **Fixed `not_equals` too**, though the bead names only `equals`. Same root cause,
  symmetric, and leaving the sibling broken (always-shown) would be a known bug.
- **Scope check on the backend:** confirmed the backend has NO runtime show_if
  evaluation (`form_models.py` only validates that `show_if.field` references
  exist; it never evaluates visibility). The frontend `shouldShowField` is the only
  conditional-visibility evaluator, so this is the complete runtime fix -- no
  backend change needed.
- **Cross-effect filed, not folded:** the fix makes two previously-unreachable
  fields (`p5_line1b_language`, `p5_line2_nameofrepresentative`) reachable. The G1b
  answer key (backend/scripts/g1b_answer_key.py, bd wf3q) marked them NA WITH THE
  EXPLICIT RATIONALE that this bug hid them, so that corpus is now stale for those
  two fields. Filed bd polyglot-pdf-b7ln (under the jnjj epic) to re-derive them;
  did not expand this bead. (The three p4 fields stay NA -- they have an
  independent gate, `p4_checkbox1 = No`.)

## Lessons

A renderer's conditional-visibility operators must account for the SHAPE of the
trigger value, not just its identity. A checkbox group's value is an array, so any
operator comparing it to a scalar (`equals`, `not_equals`) silently no-ops unless
it branches on `Array.isArray`. The `contains`/`is_checked`/`in` operators already
did; `equals`/`not_equals` were the holdouts. When a field can be a multi-select,
audit every operator that compares its value.

## Doc freshness

Bumped `docs/components/schema-forms.md` -- it tracks `validation.ts` (this
branch's only source change) and was stale. Added a current-state sentence to the
"Conditional fields" section documenting the array-trigger membership semantics
for `equals`/`not_equals`, and re-stamped `*Last updated:*` to 2026-06-28 pointing
at this entry (dropped the long historical `Prior:`/multi-pointer chain per the
current-state-only doc rule).

The prep flagged ~20 other STALE docs; all track `backend/` files this branch did
NOT touch (they were stale before this work) -- left as-is.

Beads housekeeping: closeout prep surfaced orphan `jnjj.45` (secretary build,
merged to dev via PR #257 but left in_progress). I did NOT close it -- it is
blocked by an open issue `p68s`, and force-overriding a dependency block on
another person's bead is a structural call on the secretary epic, not mechanical
cleanup; surfaced to the maintainer instead. The 3 stale in_progress beads (`hrn`,
`jf6w`, `ue5s`) are the maintainer's own active epics -- left.

## Files touched

- `frontend/src/schema-forms/utils/validation.ts` -- `equals`/`not_equals` handle an array (checkbox-group) trigger by membership.
- `frontend/src/schema-forms/utils/validation.test.ts` -- new `shouldShowField` describe block (6 cases; first tests for this function).
- `docs/components/schema-forms.md` -- conditional-fields current-state prose + stamp.
