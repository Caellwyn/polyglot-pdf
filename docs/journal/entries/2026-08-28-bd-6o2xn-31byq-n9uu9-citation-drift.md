---
date: 2026-08-28
bead: polyglot-pdf-6o2xn, polyglot-pdf-31byq, polyglot-pdf-n9uu9
title: "docs: fix drifted callback_handler.py citations across three docs"
tags: [doc-freshness, citations]
---

## Trigger

Three independent bead-catcher findings, all `callback_handler.py` line-number
citations that had drifted: `docs/technical_guide.md` (bd `n9uu9`),
`docs/components/config-deployment.md` (bd `31byq`), and
`docs/sprint_13_multilingual-ux_plan.md`'s "Threading map" paragraph (bd
`6o2xn`), which the bead itself flagged as likely having more drift in its
wider citation cluster.

## What shipped

- `n9uu9` (`technical_guide.md:448` for `on_tool_call`): **already fixed**,
  closed without a further edit. Bd `polyglot-pdf-u83oe`'s citation-repair
  chain (merged into `dev` earlier this session) had already re-anchored this
  exact citation to the symbol name `CallbackHandler.on_tool_call` with no
  bare line number -- verified no `callback_handler.py:448` string remains
  anywhere in `docs/`.
- `31byq` (`config-deployment.md:466` for the VFF_DEV_LOGGING comment): the
  cited line was `on_tool_call`'s signature closing paren, not the comment.
  Found the real comment (the "LOGGING POLICY (HIPAA COMPLIANCE)" block
  inside `on_tool_call`) and re-anchored to it by name.
- `6o2xn` (`sprint_13_multilingual-ux_plan.md`'s Threading map, `:1417/:1447`
  named in the bead plus its self-flagged wider cluster): verified EVERY
  citation in the paragraph against current code, not just the two named --
  10 of the ~12 citations had drifted, several onto completely unrelated code
  (a section-restart pointer reset, a disclaimer-message send). Rewrote the
  whole paragraph with symbol-name anchors throughout instead of patching
  individual line numbers.

## Lessons

**A bead naming two citations as an example is a sample, not the whole
defect -- check the container, not just the named instances.** `6o2xn`
explicitly said "the wider citation cluster ... should be spot-checked at
the same time since it is likely similarly stale," and it undersold it: of
roughly a dozen citations in one paragraph, all but two had drifted, several
onto code that has nothing to do with the claim being cited (CLAUDE.md scar
#7: enumerate the set, not the named instance). This is the same shape as
this session's earlier `webFormConnection.ts`/`technical_guide.md` citation
sweep -- a single edit to a heavily-cited file breaks far more citations
than a mechanical checker (which only catches EOF/blank-line landings, never
"real code, wrong code") can see.

**A closed-but-still-open bead is real, and closing it as already-satisfied
is the correct move, not a wasted claim.** `n9uu9`'s exact fix had already
landed via a different bead's ripple effect before this one was ever picked
up. Verifying that (rather than re-doing the same edit) avoided a
no-op diff and confirmed the earlier fix actually stuck.

## Files touched

- `docs/components/config-deployment.md` -- VFF_DEV_LOGGING citation
  re-anchored to the comment block by name.
- `docs/sprint_13_multilingual-ux_plan.md` -- Threading map paragraph
  rewritten with symbol-name anchors throughout, replacing ~10 drifted
  line-number citations.
- `polyglot-pdf-n9uu9` closed with no code change (already fixed upstream).
