---
date: 2026-08-24
bead: polyglot-pdf-tgohh
title: "docs(agents): the bead carve-out names bd create/note/dolt push but not bd dolt pull, which every reviewer runs first"
tags: [doctrine]
---

## Trigger

The "THE ONE EXCEPTION: filing a bead" read-only carve-out in all three
reviewer agents and `docs/doctrine/review-flow.md` enumerated three
sanctioned commands (`bd create` / `bd note` / `bd dolt push`), but the
sanctioned filing sequence documented further down every one of those
same files runs a fourth command first: `bd dolt pull && bd create ...
&& bd dolt push`. The enumeration read as exhaustive to exactly the
literal-minded reader this rule exists for -- the bug it fixes was a
reviewer reading a rule literally in the first place.

## What shipped

A parenthetical added to all four files' carve-out explaining `bd dolt
pull` needs no exception at all: unlike the other three commands, it
writes only to `.beads/dolt/` and `.beads/embeddeddolt/`, both gitignored,
never a tracked path (verified against `.beads/.gitignore` and `bd dolt
pull --help`'s own description before writing the claim). A pinning
assertion added to the existing `test_body_carves_out_bead_filing` test,
mutation-verified.

## Lessons

**The more accurate fix wasn't the first one suggested.** The bead itself
offered "add `bd dolt pull` to the enumerated list" as the lead option.
Doing that literally would have been WRONG, not just imprecise: the list's
three commands are exceptions because they write to a TRACKED path
(`.beads/`) that the blanket read-only rule would otherwise forbid.
`bd dolt pull` doesn't share that justification -- it writes only to
gitignored paths, so it was never actually a candidate for the same
exception in the first place. Appending it to the list would have
misrepresented why it's safe. The fix that's actually correct explains the
DIFFERENT reason it's fine, rather than folding it into a category it
doesn't belong to.

## Doc freshness

`docs/standards/bead-tiers.md` tracks the whole `.claude/agents/`
directory and was flagged stale purely by this commit's mtime; its actual
content (bead-tier routing conventions) makes no claim this diff touches,
and is separately known pre-existing-stale (beads `polyglot-pdf-2ua0w`,
`polyglot-pdf-s54c`). No action needed here.

## Files touched

- `.claude/agents/cross-surface-reviewer.md`, `docs-reviewer.md`,
  `fresh-eyes-reviewer.md`, `docs/doctrine/review-flow.md` -- carve-out
  parenthetical
- `tests/test_reviewer_agents_are_read_only.py` -- new pinning assertion
