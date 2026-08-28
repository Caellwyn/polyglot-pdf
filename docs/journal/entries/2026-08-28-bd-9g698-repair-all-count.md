---
date: 2026-08-28
bead: polyglot-pdf-9g698
title: "fix(schema-editor): Repair-all counts only the errors the repair pass can fix"
tags: [schema-editor, ux]
---

## Trigger

The editor's "Repair all (N)" button counted ALL lint ERRORs, not just the
ones the deterministic repair pass can actually fix. Since bd `ot284`, a
select's `option-value-missing` is deliberately NOT repairable -- only the
author can supply the PDF export code -- so an author whose kit had only
that defect saw "Repair all (1)", clicked it, waited out a round trip, and
the count stayed at 1 with no explanation. This is the normal path for
adding a dropdown choice (bd `alzbr`'s "+ Add Option" intentionally mints an
empty value precisely so this ERROR stands as the "supply the code"
signal), not an edge case.

## What shipped

`ValidationPanel`'s `errorCount` now subtracts findings the repair pass
cannot act on. The first draft only excluded `option-value-missing` on a
`select`-type field; Opus cross-surface review correctly flagged this as
an instance of CLAUDE.md scar-tissue #7 (fix the whole set, not one member)
-- the bead's own exit criteria said "at minimum," anticipating siblings.

Enumerated the complete set by EXECUTION, not by reading comments: every
ERROR-severity rule `schema_lint.py` can emit was run through
`schema_repair.py`'s `repair()` against a synthetic finding (dumpless, the
common frontend lint path), and the empirical result -- not any prose
claim -- decided inclusion. Four more rules never clear:
`hidden-with-show-if`, `value-arity`, `ref-unresolved-field`,
`to-review-pending`.

Also empirically DISPROVED an assumption before it shipped:
`option-value-slug` on a select looked like it should mirror
`option-value-missing`'s carve-out, but direct execution showed a dumpless
repair genuinely mints it (the same as radio/checkbox_group) -- the
carve-out for THIS rule is dump-conditional (`pdf_choice_values` treats a
missing dump as "no evidence"), not type-conditional. Excluding it would
have under-counted a repair that actually works, the opposite failure
direction from this bead. Left it out of the exclusion set, with the
reasoning recorded in the code.

`field-unbacked` (and `field-claim-unresolvable`, found the same way) are
also NOT excluded, for a different reason: `repair()` doesn't silently
no-op on either, it RAISES (`RepairError`), which `editor_kit_routes.py`
already converts to a real 422 the author sees -- a different,
already-handled failure mode than the silent no-op this bead targets.

A second Opus cross-surface round found two more gaps in the same
enumeration, both from a mistaken assumption the first empirical sweep
made: it only tested the DUMPLESS repair path, but `ValidationPanel` uses
the kit-scoped, dump-loaded route whenever a kit is open -- which is the
ONLY way its `onRepairAll` prop is ever wired up (`App.tsx` gates it on a
selected kit), making dump-present the NORMAL case, not an edge case.
Re-running the sweep WITH a dump found `dump-widget-multiclaim` never
clears either, added to the rule-level exclusion set. Separately,
`condition-malformed` turned out to carry six sub-shapes reachable through
the editor's normal flow (a non-dict condition, a non-list bucket, a
non-dict bucket member, an empty bucket, a missing operator, a missing
field reference) -- only two (non-dict condition; missing field reference)
survive repair() unchanged; the other four clear. Excluding the whole rule
id would have hidden four working repairs, so the two unrepairable
sub-shapes are matched by their exact message text instead (the only
sub-shape signal `LintFinding` carries).

A third round found the same message-based approach was tempting to
over-apply: `value-arity` LOOKED like another condition-malformed-style
split (three sub-shapes, one plausible-sounding candidate for "clears").
Constructing the fixture with a made-up operator name made one sub-shape
APPEAR repairable -- but that was an artifact of the fake operator name
(lint's own unknown-operator check would reject it before value-arity is
ever evaluated), not a real code path. The round-3 conclusion was that
`value-arity` was, after all, a correct wholesale exclusion -- but a
FOURTH round (re-testing each of the three sub-shapes in full isolation,
one schema and one finding at a time, rather than trusting a batched
result) found that conclusion itself was wrong: a stray value left on a
no-value operator (`is_empty`/`is_not_empty`/`is_checked`) genuinely IS
silently cleared by `repair()`'s `_rewrite_atom` (which unconditionally
drops the stray value), while the other two sub-shapes (a list-arity
operator missing its list; a scalar-arity operator given a list or
nothing) genuinely are not. `value-arity` is split the same way
`condition-malformed` is, matching only the two truly-unrepairable
sub-shapes.

## Lessons

**"At minimum" in an exit criterion is a flag that the author expects more
instances, not a scope boundary.** The first draft read the phrase as
permission to stop at one, and cross-surface review correctly called that
out as the exact enumerate-the-set trap CLAUDE.md warns about. The fix
this time was to make the enumeration EMPIRICAL: run every candidate rule
through the actual repair function rather than trying to reason about it
from reading `schema_repair.py`'s prose, which turned out to be
necessary -- reading the code alone would have wrongly excluded
`option-value-slug`, since its comments read as though it shares the same
select-only carve-out `option-value-missing` has, when direct execution
shows it does not.

**"Empirical" only holds if the fixture is real AND fully isolated.** The
`value-arity` saga took two separate corrections. First: a synthetic test
fixture using a made-up operator name made one sub-shape look repairable,
when the actual code path (lint's own unknown-operator check firing
first) can never reach `value-arity` with that operator at all -- fixed
by re-testing against real operator names. Second, and more subtle: even
with real operators, testing all three sub-shapes and drawing one
combined conclusion ("all three survive unchanged") was itself wrong --
one sub-shape genuinely clears. Only re-testing each sub-shape completely
alone, one schema and one finding at a time, surfaced it. Both mistakes
share the same root: the empirical method this bead's whole approach
relies on is only as trustworthy as the isolation of each individual test
-- an invented input can silently test a code path that does not exist,
and a batched or under-isolated result can silently launder one
sub-shape's true behavior into a false conclusion about a whole set.

The `legacy-trigger-side-logic` round repeated the SAME lesson a third
way: a fixture using an invalid data shape (the wrong key structure for a
`controls_fields` entry) can look like it exercises the real rule while
actually testing nothing -- the finding fired identically for the invalid
shape as for a real one, so the test appeared to pass without ever
reaching the code path it claimed to verify. Across all five rounds, the
common failure was never the REASONING (each round's logic, once the
inputs were right, was sound) -- it was always an unverified assumption
about whether the INPUT actually represented the real thing being tested.

**Eight rounds, one bug enumeration -- and that is fine, not a failure of
process.** This session's own doctrine says enumerate the set before
fixing any of it; it does not say a set this large and this entangled
with backend internals gets enumerated correctly in one pass. Every round
found a real, distinct gap (not a restatement of the same finding in a
new location, which is the actual warning sign CLAUDE.md names) -- the
cost was eight adversarial review rounds, not a shipped bug. Rounds 7-8
(Opus cross-surface review) were a different shape than rounds 1-6's
isolation mistakes: genuinely-missed cross-file interactions (two
findings on one field distinguished only by an unused `path` field, an
entirely unenumerated rule, and a Python/JS truthiness mismatch) --
confirming that even after several rounds of fixture-validity vigilance,
the review layer that traces the diff OUT into consumers and re-derives
the rule list from scratch still had things the inner review's
per-rule-in-isolation testing could not surface on its own.

**Porting a Python truthiness check to JavaScript is its own distinct
trap, separate from every fixture-validity mistake earlier in this same
bead.** `control.get(k)` is falsy for `None` AND for an empty list in
Python; the natural-looking JS translation (`c.locks || c.makes_optional`)
is NOT falsy for an empty array -- `[]` is truthy in JavaScript. This
looks like the same "isolation" family of mistake as rounds 3/4/6, but it
is actually a different failure mode: those were about constructing a
fixture that did not represent the real input space; this one was about
correctly translating a boolean rule ACROSS languages with different
truthiness semantics for the exact value this rule cares about. Both are
real risks whenever frontend code re-derives backend logic, but they are
worth naming separately rather than filing under one lesson, because the
fix for one (test with real backend inputs) does not by itself catch the
other (know where the two languages disagree).

A fifth Opus round found a rule missing from the enumeration ENTIRELY:
`legacy-trigger-side-logic` (a schema still carrying the removed
`controls_fields`/`conditional_fields` keys) had no classification
anywhere. Investigating it surfaced a genuine sixth-round correction of
its own: `controls_fields` entries carry an ACTION KEY (`shows`/`hides`/
`unlocks`/`locks`/`makes_required`/`makes_optional`); repair() mirrors 4
of the 6 onto the target field's `show_if`/`require_if`/
`conditional_behavior`, but `locks`/`makes_optional` have NO v2
target-side encoding and are explicitly retained on the field (repair's
own comment: "needs human review"). The finding's message is IDENTICAL
regardless of which action triggered it, so message-matching (the
technique used for `condition-malformed`/`value-arity`) cannot work here
-- the exclusion instead inspects the TRIGGER field's own
`controls_fields` array for a `locks`/`makes_optional` key, the same
field-cross-reference approach `option-value-missing`'s select carve-out
already uses.

Getting this right took a second attempt within the same round: an
initial verification pass used an invalid `controls_fields` entry shape
(`{"action": "locks", ...}`, which is not how the schema actually encodes
an action -- the real shape is `{"locks": [target_ids]}`), which made
ALL SIX actions look like they cleared. Only re-testing with the correct
shape (and a schema built from `schema_lint.py`'s own emission-site
comments, not guessed) revealed the true 4-clear/2-stand split.

A seventh round (Opus cross-surface review, spotting real cross-file
inconsistencies rather than another sub-shape-isolation mistake) found two
more genuine gaps: (1) a field carrying BOTH `controls_fields` (with an
unconvertible action) AND `conditional_fields` gets TWO
`legacy-trigger-side-logic` findings sharing one `field_id`, distinguished
only by `path` -- round 6's field-cross-reference excluded both, but
`conditional_fields` is ALWAYS unconditionally dropped by repair() (a
plain legacy id list, nothing to convert into), so the second finding was
wrongly hidden. Fixed by scoping the exclusion to findings whose `path`
ends in `.controls_fields` specifically, not merely "this field has one
somewhere." (2) `operator-trigger` -- another rule this enumeration had
missed entirely -- carries two sub-shapes exactly like
`condition-malformed`/`value-arity`: a trigger field whose TYPE can never
trigger any condition (unrepairable) vs. an operator merely invalid for an
otherwise-legal trigger type (repair() DOES alias it). Split by message
substring the same way.

An eighth round (a second Opus cross-surface pass, re-verifying the round-7
fixes rather than a fresh sweep) found one more real gap in round 6's
original code: the unconvertible-action check tested key PRESENCE
(`'locks' in c`) where the backend's rump-retention tests key TRUTHINESS
(`control.get(k)`), so a `locks: []` (explicitly present, but empty) was
called unrepairable when repair() actually clears it (an empty list is
Python-falsy, so `control.get(k)` is `None`, the action is dropped from
the rump, and the whole `controls_fields` entry is popped). Fixed by
checking Python-style truthiness explicitly -- and that fix itself needed
a second attempt: a first pass used `c.locks || c.makes_optional`, which
is WRONG in JavaScript specifically, because `[]` is truthy in JS
(`!![] === true`) even though it is falsy in the Python code being
mirrored. The corrected version checks array length explicitly rather
than relying on either language's native truthiness, since the two
disagree on precisely the input this fix cares about.

Three pre-existing, out-of-scope findings surfaced during the empirical
sweeps were filed rather than folded in: `polyglot-pdf-7fezk`
(`schema_lint.py`'s module docstring omits `to-review-pending` from its
rule catalog), `polyglot-pdf-2sli8` (a mixed atom+bucket condition
shape silently loses data in `_rewrite_condition`, found while re-running
the sweep, reproduces identically on `origin/dev`), and
`polyglot-pdf-v3qvi` (this diff's whole classification has no compile-time
or test-time link to the backend rule ids/messages it mirrors -- a future
rename or reword on either side silently reverts this bead's fix with both
suites green; left as a genuine follow-up rather than over-engineering a
shared-contract test into this already-large PR). A fourth finding (a
stale comment citing a nonexistent `controls_fields.py`) was fixed inline
in round 7 since the same comment block was already being rewritten.

## Files touched

- `schema-editor/src/components/ValidationPanel.tsx` -- errorCount now
  excludes select-scoped `option-value-missing`, four unconditionally-
  unrepairable rules, two `condition-malformed` sub-shapes, two
  `value-arity` sub-shapes, one `operator-trigger` sub-shape (all matched
  by message text), and a path-and-field-cross-referenced
  `legacy-trigger-side-logic` carve-out scoped to the exact
  `.controls_fields` finding on a trigger field whose `controls_fields`
  carries an unconvertible action (not its `.conditional_fields` sibling,
  which repair() always fixes); tooltip corrected to name the actual
  scope.
- `schema-editor/src/components/ValidationPanel.test.tsx` -- 23 new tests
  across eight rounds: select-scoped option-value-missing (3), four
  rule-level exclusions (4), two condition-malformed sub-shapes plus one
  confirming a repairable sub-shape still counts (3), two value-arity
  sub-shapes plus one confirming the third still counts (3), two
  legacy-trigger-side-logic unconvertible actions plus two confirming
  convertible actions still count (4), and one confirming option-value-slug
  on select is deliberately NOT excluded (1). Mutation-verified per
  addition, each round, in both directions where applicable.
