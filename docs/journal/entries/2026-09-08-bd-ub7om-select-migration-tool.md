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

**A cleared code and a missing code are different in the editor but the same
on disk.** In the editor, `pdf_on_value: ''` is a v2 option with no code. On a
kit file, `{value: 'AL', pdf_on_value: ''}` is the half-migrated shape lint
rejects; treating it as legacy (so the code moves) is what preserves the code.
Pinned; the mutant that treats empty as v2 reddens it.

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

## Files touched

- `scripts/migrate_select_on_values.py` (new)
- `backend/models/conditional_vocabulary.py` -- `mint_select_slugs(..., reserved=())`
- `tests/test_migrate_select_on_values.py` (new)
