---
date: 2026-08-17
bead: polyglot-pdf-x82ii
title: "docs: fix cross-doc contradiction + widespread citation drift found by prior review"
tags: [conventions, testing]
---

## Trigger

The Opus cross-surface reviewer, reviewing PR #590 (a bundle of 8 unrelated
docs-nit beads picked from the ready queue), traced the corrected
`initial_field_hint` claim in `ws-protocol.md` (bd e3t7) out into sibling docs
and found it contradicted `stateless-architecture.md`. While doing that trace
it also found `ws-protocol.md`'s entire line-citation set had drifted off a
single code motion in `websocket_routes.py`, and that `voice-ai.md` still
described `ask_secretary` as recall-only (bd 2k00x had fixed only one of two
sites carrying that stale claim). Three beads filed: h5v7h, 9sz5y, x82ii.

## What shipped

- **h5v7h.** `stateless-architecture.md` claimed the warm-reconnect handshake
  frame omits `initial_field_hint`. False for the JIT/DTI builder (the
  production default) since bd jnjj.9 (A2) -- it sends the field on every
  connect, not only a section switch. Corrected to match `ws-protocol.md` and
  the shipped `schemaFormState.ts`; the `section_id` half of the original
  claim was already accurate and is unchanged.
- **9sz5y.** `voice-ai.md`'s `ask_secretary` bullet named only the recall use.
  Now names all three shipped uses (recall, field-navigation identification,
  official instruction text quoted back, bd wsao.8) and the hedge-and-defer
  relay contract `test_secretary_scrivener_boundary.py` pins. Swept
  `docs/components/`, `docs/standards/`, `technical_guide.md`, and `.claude/`
  for any other site describing fewer than three uses -- none found.
- **x82ii.** Every `(line N)` / `:N` citation in `ws-protocol.md` had drifted
  ~17 lines off one code motion in `websocket_routes.py`, plus several
  independently-drifted citations into `callback_handler.py`,
  `request_coordinator.py`, `form_filling_service.py`, `schemaFormState.ts`,
  and `webFormConnection.ts`. One citation (the secretary-catalog renderer)
  named the wrong FILE, not just a wrong line -- the doc's citation chain
  skipped `text_ai_gemini.py` (where `render_static_catalog(schema)` is
  actually called) entirely. Wrote a small verification script that checks
  every claimed `(file, line, expected substring)` triple against the live
  source before editing anything, ran it, fixed every failure, then re-ran it
  clean (~80 citations verified). Widened the fix into the adjacent
  WS-handshake block, "3. WS control messages", and "4. Backend <-> Gemini
  Live" blocks of `technical_guide.md`, which carry the identical drift off
  the same code motion. Sections 5 ("Fill round-trip") and 6 ("Confirmation
  audit trail") of that file carry the same drift class but are a different
  topic outside this bead's stated scope -- filed separately as bd bxr3p
  rather than expanded into here (the bead's own comment explicitly scoped the
  widening to "the WS-handshake block of technical_guide.md").

Fresh-eyes (Sonnet) found one non-blocking nit: the `technical_guide.md`
freshness stamp didn't credit a small citation fix (the
`SchemaFormState.fieldValues` producer line, which sits at the boundary of the
widened block) that the diff had actually made. Fixed in a follow-up
non-behavioral commit in the same branch (does not invalidate the clear). The
Haiku `docs-reviewer` (docs-only diff, no source files touched) then returned
`NO-GAPS` with no findings.

## Lessons

- **A wrong-file citation is a different failure class from a wrong-line
  citation, and worth naming as such in the fix.** `render_static_catalog`
  being cited via `secretary_context.py` instead of `text_ai_gemini.py` (where
  it's actually called) wasn't caught by eyeballing nearby line numbers --
  only by reading what the cited function actually does and grepping for its
  real call site. A drift-fix pass that only re-derives line NUMBERS against
  the same file names would have missed this one.
- **Verify-before-edit at scale needs a script, not memory.** With ~80
  citations across 4 files, hand-tracking which had been checked and which
  hadn't would have reproduced exactly the "recall harder instead of
  enumerate" failure mode CLAUDE.md scar #7 describes. A ~100-line Python
  script asserting `needle in line[N-1]` for every citation, run once before
  any edits and once after, made the set complete and re-verifiable in
  seconds rather than trusted from memory.
- **A bead's own scope-widening comment is the boundary, not an invitation to
  keep going.** The bead explicitly widened its own scope once (to include
  `technical_guide.md`'s WS-handshake block specifically); continuing past
  that into sections 5-6 because "it's the same doc, same drift class" would
  have been scope creep past what was actually authorized. Filing bxr3p
  instead of silently expanding kept the PR reviewable and matched the
  decide-or-file rule for out-of-scope-but-not-a-step-2-question work.

## Doc freshness

- **Bumped:** `docs/standards/stateless-architecture.md`,
  `docs/components/voice-ai.md`, `docs/standards/ws-protocol.md`,
  `docs/technical_guide.md` -- all four re-stamped to today with a prose
  summary of what changed; `check_doc_freshness.py` confirms all four OK.
- **Reviewed and left:** `docs/technical_guide.md` sections 5-6 retain their
  pre-existing citation drift, deliberately, per bd bxr3p (filed this session).

## Files touched

- `docs/standards/stateless-architecture.md`
- `docs/components/voice-ai.md`
- `docs/standards/ws-protocol.md`
- `docs/technical_guide.md`
