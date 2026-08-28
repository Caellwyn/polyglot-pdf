---
date: 2026-08-28
bead: polyglot-pdf-7fezk
title: "docs(schema-lint): module docstring's Rules catalog was missing 3 real rules, now mechanically pinned"
tags: [schema-lint, docs, testing]
---

## Trigger

`backend/services/schema_lint.py`'s module docstring catalogs every rule id
`lint_schema()` can emit. The bead reported `to-review-pending` missing --
found while independently re-verifying bd `9g698`'s empirical rule sweep,
which needed to grep for the rule rather than read it off the docstring.

## Enumerate the set first (CLAUDE.md scar tissue #7)

The bead named one instance. Grepping every `LintFinding(SEVERITY_*, "...")`
call site and diffing against the docstring's enumerated list found the set
was actually missing **two** entries, not one:

- `to-review-pending` (the bead's reported instance)
- `audit-identity-no-edition` (an unrelated, independently-drifted gap)

Writing a mechanical parity test (see below) then found a **third**, larger
gap the manual grep missed: the docstring's `translation-*` wildcard line
documents `TRANSLATION_FLAG_RULES`, but there was no equivalent wildcard for
`GUIDANCE_FLAG_RULES` (`instructions-rectified`, `instructions-ungrounded-dropped`,
`instructions-enrich-unavailable`, re-emitted from
`authoring.instructions_enrich.flags` the same way translation flags are).
That taxonomy had zero documentation in the module docstring at all.

## What shipped

- Three docstring additions: `to-review-pending`, `audit-identity-no-edition`,
  and an `instructions-*` wildcard entry (mirroring the existing `translation-*`
  line's style) documenting the guidance-flag taxonomy.
- A new mechanical test,
  `test_the_module_docstring_lists_every_rule_the_backend_emits` in the
  existing `backend/tests/unit/test_lint_rule_parity.py` (reusing that file's
  `_backend_rule_ids()` extraction, which already walks inline emission sites
  plus both flag-taxonomy frozensets). Pins the set instead of the instance:
  a future rule added without a docstring entry now fails CI, rather than
  waiting for someone to grep for it again.

## Lessons

The bead's own scope (one missing rule) undersold the actual drift. A second
gap was findable by the same grep the bead used, just not run exhaustively.
The third gap -- an entire taxonomy with no wildcard line -- was invisible to
manual re-reading of the docstring (nothing there hints at what's absent) and
only surfaced once the comparison was made mechanical: the first test-run
failed on all three `GUIDANCE_FLAG_RULES` members, which forced tracing where
they were emitted from and noticing the docstring's `translation-*` line had
no sibling for them.

The test's wildcard handling is written generically (derive prefixes from the
docstring's own `PREFIX-*` lines, don't hand-list `"translation"` and
`"instructions"`), so a third taxonomy added later needs a docstring line but
not a test edit -- narrowing the fix to the code, not the description of
today's two taxonomies.

Mutation-verified: reverting each of the three docstring additions in turn
(the `to-review-pending` entry, the `audit-identity-no-edition` entry, and
the `instructions-*` wildcard line) reddened the new test with exactly the
expected missing-rule-id list each time; restored and re-confirmed green.

## Files touched

- `backend/services/schema_lint.py` -- 3 new/expanded docstring 'Rules' entries.
- `backend/tests/unit/test_lint_rule_parity.py` -- new pinning test plus two
  small helpers (`_docstring_rule_ids`, `_docstring_wildcard_prefixes`).
