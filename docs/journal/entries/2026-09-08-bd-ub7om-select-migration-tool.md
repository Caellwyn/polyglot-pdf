---
date: 2026-09-08
bead: polyglot-pdf-ub7om
title: "feat(scripts): migrate_select_on_values.py -- move a select's export code into pdf_on_value and mint its slug"
tags: [form-kits, schema, tooling, testing]
---

## Trigger

PR 3a of the g2fpr epic (`polyglot-pdf-ps4hf`). PR 1 taught the filler and
`/resume-form` to read a select's `pdf_on_value`; PR 2 taught the extractor,
the editor and the extraction prompt to write it; PR 3c made a saved session
survive the change. Existing kits -- the maintainer's `i-90_v2` above all --
still keep the export code in `option.value`. This is the tool that moves it.

## What shipped

`scripts/migrate_select_on_values.py`: for every select option WITHOUT a
`pdf_on_value`, `pdf_on_value = value` (the code, verbatim) and `value =
mint_select_slugs(...)` -- kept when the code is already a slug (`'5'`),
otherwise minted from the label with a trailing `(CODE)` stripped. Every
`show_if` / `require_if` atom on that field is retargeted old -> new, on fields
and sections, scalar and list. `--kit DIR` rewrites `schema.json` in place with
an archive and a report beside it; `--in/--out` for a copy. `metadata.json` is
never opened: the readiness stamp goes stale by design and a human re-verify in
the editor mints a fresh one.

## Lessons

**The tool depends on the writer PR, so it could not be tested until that PR
merged -- and a worktree branched a day earlier did not have it.** I authored
the script and its tests against PR 2's known minter API, then waited; the
first import failure (`cannot import name 'mint_select_slugs'`) was the tell
that the worktree was on a pre-PR-2 `dev`. Stacking on the unmerged branch
would have been the trap this repo has already paid for; waiting cost nothing.

**One minter, three producers.** The extractor, the editor and this tool must
mint the same slug for the same label, or a kit migrated by one disagrees with
a kit extracted by another. The tool calls `mint_select_slugs` and adds a
`reserved` parameter for the field's already-v2 values, rather than restating
the uniqueness rule. (`migrate_schema_v2.py` still restates it -- bd
`polyglot-pdf-345mj`, filed by the PR 2 cross-surface pass.)

**A cleared code is a cleared code, on disk too -- round 3 reversed round 1.**
I had argued `{value: 'AL', pdf_on_value: ''}` on a kit file should count as
legacy so the code moves. Fresh-eyes showed the other half of that rule:
`{value: 'alabama', pdf_on_value: ''}` -- an option whose author cleared its
code -- would have had 'alabama' fabricated INTO `pdf_on_value`, a code in no
/Opt, and the report could not tell it from a legitimately kept '5'. The
consistent rule is PR 2's: legacy means the key is ABSENT; an empty code is a
v2 option with no code, left alone and NAMED in the report (`no_code`) for the
human who has to supply it. The round-1 test was flipped to the new contract,
and the mutant that restores empty-is-legacy reddens it. A rule that saves
the code in one case and invents one in the other is not a rule.

**Ambiguity has three faces.** Two legacy options sharing a code (round 1); a
legacy code equal to a v2 sibling's VALUE (round 2, a condition may mean the
v2 option); a legacy code equal to a v2 sibling's CODE (round 3, two options
would write one widget state). All three are reported and never retargeted.
Enumerating "what can a code collide with" up front would have been one round
instead of three -- scar #8 in a different costume.

**Never guess between two claimants.** A code two options share cannot be
retargeted unambiguously; the tool reports it and leaves the condition for a
human, matching `/resume-form`'s policy. The mutant that retargets anyway
reddens the pin.

**A new parameter needs its own unit test, or its first consumer's tests are
the only ones -- and they test the consumer.** `reserved` shipped with zero
direct tests; fresh-eyes reproduced the hole in one line:
`mint_select_slugs(["Five"], ["5"], reserved=["5"]) == ["5"]`. The keep
fast-path never consulted the reserved set, so a half-migrated field (the
editor's convert-on-touch leaves exactly that) could end with two options
sharing a value. A kept code that a reserved sibling already holds is now
minted from its label instead; three direct tests, and the mutant reddens two.

**"The report names every change" means NAMES, not counts.** Kept numeric
options were counted (`kept_as_slug: 5`) but not listed; an auditor working
from the report alone could not say which. `kept_codes` now lists them, and a
test asserts every migrated option appears exactly once, in `slug_map` or
`kept_codes`.

**`str(None)` is a key.** An id-less field was keyed as the string `"None"` in
the retarget map, so two such fields would merge maps and a condition on a
field literally named "None" would be rewritten. Guarded; the test that
reproduced it failed for exactly that reason before the guard landed.

**"Pre-existing" has to mean pre-existing on `dev`.** Round 2 filed two
bugs as out of scope because they reproduced on `9a8555a0` -- this PR's own
feature commit. Both were this diff's to fix, and both were: (1) the
ambiguity guard considered only legacy-vs-legacy duplicates, so a legacy code
equal to an already-v2 sibling's VALUE was retargeted -- a condition naming
'5' that meant the v2 option was repointed to the newcomer's slug; such a code
is now reported and left for a human. (2) Two legacy options sharing a
slug-shaped code both passed the keep fast-path and were WRITTEN with the same
value, contradicting the minter's own "uniqueness across the whole set"; only
the first occurrence is kept now, in the Python minter and in the editor's
TypeScript mirror, with the fixture shared. When a reviewer's "pre-existing"
commit hash is inside the diff under review, the finding is in scope.

**Idempotent means "migrates nothing twice", not "reports nothing twice".**
The docstring promised an empty report on a second run; a kit with a cleared
code reports that human work item every run, the same way each time -- and
should. The false promise was one round-4 finding; the other was its
consequence: the CLI printed "nothing to do" while a field still needed a
human, because only `duplicate_codes` had a stderr warning. Two kinds of
outstanding work, one warning -- scar #8 again; both warn now, and "nothing
to do" prints only when it is true.

**Count the real thing.** The plan said "4 state dropdowns x 62"; the kit has
two (`mail_state`, `phys_state`) plus the two height dropdowns: 143 options.
The reviewer caught it by running the tool on a read-only copy. The PR body
now tells the maintainer the number they will actually see.

**A counter nothing reads is a finding nobody sees.** `non_dict_options` was
tallied per field and then dropped: a select whose options are plain strings
never reached the report and never warned. Round 5 caught it -- the third
kind of outstanding human work, after cleared codes and duplicates, and the
third time this PR surfaced one kind and forgot a sibling. All three now
reach the report and the CLI; the warnings print one line per field, capped,
like `migrate_schema_v2`'s.

**An enumeration that gates only one of two doors is half an enumeration.**
Round 7 showed round 6's tuple drove the CLI print but not report INCLUSION:
the `if entry[...] or ...` gate was a second hand-kept list, the top-level
`fields_with_duplicate_codes` a second accumulator, and the header count an
implicit type dispatch. Now `_HUMAN_WORK` drives both gates, carries an
explicit per-kind counter, the top-level index is derived from the entries,
and one test pins the SET: every per-field report key is an outcome key or a
`_HUMAN_WORK` key -- a fourth key added anywhere else reddens it. The tell
that an enumeration is incomplete: you can add a member and something still
silently ignores it.

**Four rounds, one trap: fix the SET, not the instance.** Rounds 4, 5 and
6 each surfaced one kind of outstanding human work and forgot a sibling --
`no_code` got a warning while `duplicate_codes` had one; `non_dict_options`
got one while `duplicate_codes` kept its raw list dump; the per-field cap got
a trailer on one of three. Round 6's reviewer named it exactly ("the third
time this PR surfaced one kind and forgot a sibling"). The fix is scar #8
verbatim: the three kinds are now ENUMERATED in one tuple (`_HUMAN_WORK`),
printed by one helper, and pinned by one test parametrized over the tuple --
a fourth kind cannot be added without deciding how it prints, and dropping a
kind from the tuple reddens exactly its case. I should have enumerated at
round 4 the moment the second sibling appeared.

## Files touched

- `scripts/migrate_select_on_values.py` (new)
- `backend/models/conditional_vocabulary.py` -- `mint_select_slugs(..., reserved=())`
- `tests/test_migrate_select_on_values.py` (new)
- `schema-editor/src/utils/fieldGrouping.ts` -- `mintSelectSlugs` keeps only the first occurrence of a code
- `schema-editor/src/utils/fieldGrouping.selectslugs.test.ts` -- the shared fixture
