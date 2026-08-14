---
date: 2026-08-14
bead: polyglot-pdf-qd0p7
title: "docs: retire decline-era wording, fix stale citations + journal gaps (8-bead nit sweep)"
tags: [conventions, testing, refactor]
---

## Trigger

Asked to find low-complication beads to knock out -- simple, single-surface
docs nits and test-comment updates, nothing cross-surface. `bd ready` listed
several dozen `docs(...)`/`test(...)` chore/bug beads filed by earlier review
passes (mostly the 2026-08-05/06 docs audit and its follow-on reviews). Eight
were genuinely small, independent, and comment/prose-only: no shared file
except two that both targeted the same journal entry.

## What shipped

Eight beads, five files, all comment/docstring/prose changes -- no behavior
change anywhere in the diff:

- **polyglot-pdf-qd0p7** -- `test_secretary_scrivener_boundary.py`'s module
  header, allowlist paragraph, one "Layer 3" section comment, and one
  assertion message still described the retired DECLINE policy (superseded
  mid-PR on bd `rdsl` by hedge-and-defer). Reworded all four spots to match
  the shipped shape; grepped the file afterward for `declin`/`refusal` and
  confirmed every remaining hit explicitly marks the retired policy as
  retired (the exit criterion's own test). All 21 tests in the file still
  pass unchanged.
- **polyglot-pdf-2k00x** -- `tool-call-flow.md`'s `ask_secretary` table row
  named only two of the three uses the shipped `backend/config.py`
  declaration advertises (past-answer recall, field-navigation
  identification, official-instruction-text quoting -- the third landed
  under bd `wsao.8`). Fixed the row. The bead's other exit criterion (a test
  docstring) was already corrected by a prior PR (#579, bd `rdsl`) -- verified
  via `git log` on the test file before touching it, so only the doc row
  needed an edit here.
- **polyglot-pdf-1i59a** -- verified already correct. `testing.md`'s conftest
  bullet already names both of `backend/tests/conftest.py`'s autouse
  fixtures (confirmation-log isolation + the newer K_SERVICE isolation from
  bd `5xhbb`). No edit made; closing as already-resolved by earlier work that
  never closed the bead.
- **polyglot-pdf-j88ph + polyglot-pdf-oyw45** -- the bd-9feav journal entry
  (`docs/journal/entries/2026-08-06-bd-9feav-review-round-reduction.md`) had
  two staleness points, both against the SAME entry, so fixed together:
  1. The rule-2 narrative (lines 84-91) described the broad "history or
     rationale" reading the round-1 reviewer (bd `qzvz1`) caught and
     narrowed. Rewrote to state the FINAL scope -- three named chronological
     shapes, plus the explicit "design rationale is not a violation"
     carve-out -- and to name the finding that produced the narrowing.
  2. "Files touched" omitted two files the merge commit (`01ba6e05`)
     actually changed: `.claude/agents/docs-reviewer.md` and
     `docs/doctrine/review-flow.md`. Verified against `git show --stat` on
     the real merge commit rather than trusting the bead's own claim,
     since the bead descriptions themselves could have been wrong about
     which files landed. Both are now listed with a one-line note on why
     each was there.
- **polyglot-pdf-a4v4** -- `technical_guide.md` cited `PDFFillRequest` at
  `pdf_fill_routes.py:35-45`; the class body ends at line 41 (its last
  field, `form_schema`), so the range straddled into the `@router.post`
  decorator and `fill_pdf` signature below it. Fixed to `35-41`, verified by
  reading the source lines directly. The bead's second exit criterion --
  teaching the citation checker to catch this straddle class mechanically --
  is separately tracked under bd `3qgw` (a checker-development bead); out of
  scope for a doc-content fix, left open.
- **polyglot-pdf-qxad** -- `technical_guide.md`'s handshake-shape paragraph
  illustrated silent `.get()`-default degradation with "a dropped `kit_id`
  logs `form_id=\"unknown\"`". Verified against
  `form_filling_service.py:324-325`: `form_id` actually derives from
  `form_metadata.form_number`, not `kit_id` -- a dropped `kit_id` instead
  degrades to `kit_id=None`, a separate field entirely. Rewrote the example
  to name the right key and note the `kit_id` behavior as a contrast (this
  now agrees with `ws-protocol.md`, which already had it right).
- **polyglot-pdf-e3t7** -- `ws-protocol.md`'s `initial_field_hint` row
  claimed "Sent by both builders." Verified against
  `schemaFormState.ts`: `getJITHandshakePayload` sends it (since bd
  `jnjj.9`/A2), but `getHandshakePayload` (legacy) does not -- the same
  asymmetry the doc already documents correctly for `section_id` and
  `kit_id` two rows away. Corrected the row to match that pattern; the
  existing DRIFT note below it (which already scoped the A2 fix to the JIT
  builder) needed no change.

No fresh-eyes gaps found -- diff size ~40 changed lines across 5 files, all
comment/prose. Full backend suite run twice (before and after the commit):
2196 passed, 2 skipped, 0 failed both times.

## Lessons

- **A bead's own exit-criteria claim is still worth re-verifying against the
  actual commit, not just trusted.** `j88ph`/`oyw45`'s "Files touched" fix
  could have been written from the bead descriptions' own file lists, but
  those turned out to already be incomplete framing of the real diff --
  `git show --stat` on the actual merge commit was the only reliable source.
  Consistent with the standing rule (verify claims against code, not the
  brief) but worth restating: this applies to a bead's OWN prose too, not
  just the doc it's fixing.
- **"Already fixed, bead never closed" is a real and cheap-to-find category.**
  Both `1i59a` and half of `2k00x` turned out to be already resolved by
  earlier unrelated PRs that didn't reference or close the filed bead. A
  quick `git log -1` / direct read against the target file before editing
  caught both, avoiding a no-op diff and a duplicate fix.

## Doc freshness

- **Bumped:** `docs/components/tool-call-flow.md`, `docs/technical_guide.md`,
  `docs/standards/ws-protocol.md` -- all three now show OK against
  `check_doc_freshness.py`, re-stamped to today with a prose summary of what
  changed (prune-on-bump, no `Previously:`/`Earlier:` chain added).
- **Reviewed and left:** the pre-existing STALE backlog surfaced by
  `check_doc_freshness.py` (roughly 20 tier-2 docs, tracked separately under
  bd `2j8w`) is untouched by this diff -- none of those docs' `**Tracks:**`
  globs cover the files this sweep changed, and fixing them is out of scope
  for a docs-nit bundle.

## Files touched

- `backend/tests/unit/test_secretary_scrivener_boundary.py` (comment/docstring only)
- `docs/components/tool-call-flow.md`
- `docs/journal/entries/2026-08-06-bd-9feav-review-round-reduction.md`
- `docs/standards/ws-protocol.md`
- `docs/technical_guide.md`
