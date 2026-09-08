---
date: 2026-09-08
bead: polyglot-pdf-38p0y
title: "The AI-write gate was the one surface that never learned to unlock a read_only field"
tags: [testing, review]
---

## Trigger

Filed during the I-90 restore (bd `polyglot-pdf-6p77c`) and deliberately left
unfixed there: the schema half was kit data (editor-owned) and the frontend half
was an unimplemented feature, out of scope for a kit restore.

The user-visible shape: a person picks a mailing-address unit type on the I-90,
`mail_unit_number` becomes shown AND required, and the voice model is told the
field is "system-managed and cannot be filled; do not attempt to fill it again."
They are asked for a value the assistant is forbidden to write. Escapable only by
typing it manually or by `skip_field`.

## What shipped

### One rule, four surfaces, and only one of them was wrong

A `read_only` field may declare `unlock_method: flip_readonly_bit`, meaning
"being SHOWN unlocks this". Three surfaces already honored that, each with its
own private copy of the condition:

| Surface | Site | Behavior |
|---|---|---|
| UI render | `FieldRenderer.tsx:82` | lifts the disable |
| Manual typing | `FieldEditPopover.tsx:96` | allows editing |
| PDF fill | `pdf_fill_routes.py` | clears the widget bit |
| **AI write** | `validation.ts:879` | **refused, unconditionally** |

`isFieldReadOnly` returned `true` for any `read_only` field, with an in-code
comment conceding the check was unimplemented ("This would require checking all
fields with controls_fields ... For now, just return the default state").

The bead offered two options: (a) flip the two i-90 fields to `read_only: false`,
or (b) teach the gate to honor the unlock. **(b), because (a) fixes two fields
and leaves the class alive** -- and because three surfaces already implementing
the rule is strong evidence the rule is right and the fourth is the outlier.

### The rule now has one home

`declaresShownUnlock()` in `validation.ts` is the single definition; three gates
call it rather than keeping a fourth private copy:

- `isFieldReadOnly` -- the shared rule
- `checkFieldAccess` -- the by-spoken-name tool path
- `evaluateFieldAvailability` -- the locked-reason path

**Visibility is part of the condition, not an assumption.** `FieldRenderer` can
take "shown" for granted because it only ever runs on a rendered field. These
helpers are called on ANY field, so an unlock whose `show_if` has not fired still
reads as read-only. Getting that wrong would have unlocked fields the user has
not reached yet -- which is why it has its own mutation below.

### Enumerating first, per scar #8

Before touching anything I grepped every `read_only` consumer in
`frontend/src` -- seven hits across four files. That is what surfaced
`FieldEditPopover.tsx:96`, which the bead never mentioned and which already
implemented the rule correctly. Fixing only the site the bead named would have
left the codebase with two correct implementations, one shared one, and no
account of the fourth.

### Tests are synthetic on purpose

**No git-tracked kit contains a single `flip_readonly_bit` field** -- `w7` and
`f1040` both measure zero. The I-90 that motivated this bead lives in the bucket,
not in git. So a test reading a real kit would have run green on a maintainer's
disk and SKIPPED in CI: exactly the failure that shipped twice on the previous
branch (`verify-in-a-clean-clone-not-your-worktree`). The fixtures encode the
SHAPE the I-90 has, so the guard is alive in a clean clone.

16 tests, mutation-verified with five mutations, each reddening only its own:

| # | Mutation | Red |
|---|---|---|
| 1 | drop the unlock check entirely (the original bug) | 5 |
| 2 | drop the visibility requirement | 2 |
| 3 | drop the legacy `conditional_logic` alias | 1 |
| 4 | revert `checkFieldAccess` alone | 1 |
| 5 | revert `evaluateFieldAvailability` alone | 1 |

4 and 5 exist because a shared helper means one caller can regress while the
others stay green -- a single mutation of the helper would not have caught that.

### Caught by the typechecker, not by me

My first negative test asserted that `unlock_method: 'something_else'` does not
unlock. `tsc` rejected it: the field is a closed union of
`'flip_readonly_bit' | 'set_property'`, so I had been asserting against an input
the type system forbids -- a test that could never fail for a real reason.
Rewritten against `set_property`, the only other member, which is a genuinely
better test. `schema_lint.py:1040` independently confirms the expectation: any
other unlock method "lints as still-locked".

## Lessons

**When N surfaces implement a rule and one disagrees, the majority is usually
right -- but go count before assuming.** The enumeration is what turned "fix the
function the bead named" into "three call sites and a shared definition," and it
found a fourth surface the bead never knew about.

**A closed union turns a negative test into a type error.** Asserting that an
impossible value behaves safely proves nothing and cannot fail. If a negative
test needs a cast to compile, the input may not be reachable -- reach for a real
member of the union instead.

**Mutation-verify each CALLER of a shared helper, not just the helper.** The
whole point of extracting the rule was that callers could drift; a mutation of
the helper alone would have left that drift unpinned.

## Doc freshness

Checked at closeout. This change is confined to three frontend files plus a new
test; no `docs/components/*` doc tracks them in a way this change falsifies.
Nothing bumped.

## Files touched

- `frontend/src/schema-forms/utils/validation.ts` -- `declaresShownUnlock()` (the
  shared rule, both key spellings) and `isFieldReadOnly` now honoring it, gated
  on the field actually being shown.
- `frontend/src/schema-forms/utils/conditionalFieldCheck.ts` -- both refusal
  paths (`checkFieldAccess`, `evaluateFieldAvailability`) routed through the
  shared rule instead of a bare `field.read_only` test.
- `frontend/src/webFormConnection.ts` -- passes the schema's fields so `show_if`
  can be evaluated against sibling values.
- `frontend/src/schema-forms/utils/readonlyUnlock.test.ts` -- new; 16 tests over
  synthetic fixtures shaped like the I-90's fields.
