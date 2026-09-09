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

### The rule now has one home -- for the write gates

`declaresShownUnlock()` in `validation.ts` is the single definition for the three
AI-write gates, which is where the bug was. It does NOT consolidate the other two
surfaces: `FieldRenderer` and `FieldEditPopover` still carry their own copies of
the expression, so until bd `polyglot-pdf-6sfal` lands, a change to the unlock
rule must be applied in three files. My first version of this helper's docstring
claimed the consolidation was complete; the reviewer caught it, and a comment
that overstates what a diff did is worse than no comment.

The three gates it does own:

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

A sixth mutation SURVIVED, and diagnosing it was worth more than the five that
bit. Dropping the `schema.fields` argument at the `webFormConnection` call site
changes nothing, because `evaluateAtomicCondition` accepts `fields` and never
dereferences it. The argument is inert today. That is category 1 of
`surviving-mutation-three-causes` -- structurally impossible to fail, not an
untested gap -- so the correct response was to write the limit into the test
rather than invent a test for it. It is passed for correctness under a future
evaluator that does use it.

### The integration layer the unit tests could not reach

Fresh-eyes scored exit criterion 1 a FAIL, correctly. The criterion asks for a
test *driving webFormConnection's update path*; my 16 tests called the three gate
functions directly. The repo already had the pattern I needed -- a real
`WebFormConnection` over a `MockWebSocket`, with a `read_only` rejection suite for
the sibling bead one file over -- and I had not used it.

Three integration tests now drive the genuine path: the write LANDS once the
trigger is filled, is still refused before it, and a no-unlock field is still
refused however it is shown. Reverting the gate reddens them, which is what
proves they exercise the real wiring rather than the helper.

### The fix made two of my own sentences false

Round 2 found the sharpest thing in this bead: the change falsified prose that
shipped in the SAME branch.

`schema_lint.py`'s remedy for `readonly-conditional-no-unlock` told authors that
an unlock "lets the PDF filler clear the bit, but the voice assistant is still
refused, so a REQUIRED field stays unfillable" -- and therefore to just clear
`read_only`. That was true when I wrote it, four commits earlier, and false the
moment the AI-write gate learned to honor the unlock. The linter was steering
authors away from the mechanism this bead exists to repair, and toward dropping
the form's own lock. Nothing pinned the message text, so nothing caught it.

It now describes both remedies accurately, and a new test pins what the sentence
MEANS: an allowlist of the sanctioned remedies plus a no-residue check for the
superseded claim. Banning one phrasing would be a synonym away from defeat. Both
halves mutation-verified separately -- swapping the working-unlock clause reddens
the allowlist, and re-adding "still refused" alongside the allowlisted phrases
reddens the residue check.

The same staleness hit `test_form_models_v2.py`'s docstring, which asserted twice
that `isFieldReadOnly` blocks the AI write regardless of unlock. Correcting it
surfaced something better than a prose fix: the guard checks `copy_to` and not
`unlock_method`, and that narrowness USED to be a consequence of the frontend's
behavior. Now it is a live design question -- a required read_only field carrying
a valid unlock is arguably fine, and the guard would still flag it. No tracked kit
has that shape (w7's offender declares no unlock at all; f1040 has no read_only
fields), so nothing is mis-flagged today. The docstring now names the question
instead of implying the answer, and it rides on bd `polyglot-pdf-cgb5a`.

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

**A test that calls the helper is not a test of the feature.** Unit tests over
the three gate functions cannot see the code that decides whether to call them.
When a bead's exit criterion names an integration point, satisfying it at a lower
layer is a narrowing -- and the honest move is to check whether the repo already
has a harness for that layer before declaring the substitution necessary. It did.

**A fix can falsify prose elsewhere in its own branch.** The lint remedy was
written four commits before the fix that made it wrong, in the same PR. The
enumeration reflex (scar #8) is usually aimed at code; it applies just as well to
every sentence that explains why the old behavior was the way it was. After
changing a behavior, grep for text that ASSERTS the old one -- especially text
that tells a human what to do about it.

**Do not claim a consolidation you did not perform.** The helper's first docstring
said the rule "lives here so the surfaces cannot drift apart again" while two
surfaces kept their own copies. That sentence would have taught the next reader
to change one file and believe they were done.

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
- `frontend/src/webFormConnection.aivalidation.test.ts` -- three integration tests
  driving a real `WebFormConnection` through `update_form_fields`, added after
  fresh-eyes correctly scored criterion 1 a FAIL.
- `backend/services/schema_lint.py` -- the `readonly-conditional-no-unlock`
  remedy, which this branch itself had made false.
- `backend/tests/test_schema_lint.py` -- a pin on what that remedy MEANS
  (allowlist + no-residue), mutation-verified in both directions.
- `backend/tests/test_form_models_v2.py` -- docstring only; states the current
  behavior and names the now-open carve-out question. No logic change.

### Exit criterion 2 is not satisfied by this PR, deliberately

Worth stating plainly rather than burying. Criterion 2 asks for a test pinning
the complete set of read_only fields that are require_if/show_if-gated with no
copy_to source. That guard EXISTS -- but it shipped in PR #745, it is already on
`origin/dev`, and this branch does not touch it. This PR contributes nothing
toward criterion 2, and the shipped guard does not cover `show_if` as the
criterion's wording asks.

The criterion was written expecting the guard to be built here; it was built
earlier instead. So the criterion reads as stale rather than unmet -- but that is
a judgment, and the honest record is that this PR closes a bead one of whose two
criteria it does not satisfy. The uncovered half is filed as
`polyglot-pdf-cgb5a`. If the bead should stay open until that lands, this is the
paragraph that says so.

## Deferred

- `polyglot-pdf-6sfal` -- fold `FieldRenderer` and `FieldEditPopover` onto
  `declaresShownUnlock` so the rule lives in one file rather than three.
- `polyglot-pdf-cgb5a` -- the required+read_only guard (already in `dev`, not
  this diff) never inspects `show_if`, and its `require_if` half is
  mutation-blind on both tracked kits. Pre-existing, so filed rather than fixed
  here.
