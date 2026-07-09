---
date: 2026-07-09
bead: polyglot-pdf-3ioz
title: "docs(editor): in-app guided help overlay for contractors (sectioned, tier-aware)"
tags: [conventions, testing]
---

## Trigger

The schema editor is powerful but overwhelming for a new contractor, and its
only in-app orientation was `HostedGuide` -- a one-time 3-step popup (pick a form
/ fix fields / save + mark complete) that never explained the actual work: what
"Instructions" and "Format Hint" do, conditional logic, controls, moving or
reordering fields, checkbox-group consolidation, or the author-side extraction
flow. The maintainer asked for a clear, contractor-facing guide and, when given
the choice, picked an in-app guided-help overlay (over a standalone doc) covering
the full author + editor workflow, with two explicit emphases: explain
Instructions/Format Hint as AI guidance, and make Extraction its own section that
stresses attaching the official instructions PDF. Part of epic polyglot-pdf-92qe
(hosted schema editor for contractor collaboration).

## What shipped

`schema-editor/src/components/HostedGuide.tsx` reworked from a flat `STEPS` list
into a sectioned, navigable help panel: a left rail of section links plus a
scrolling content pane, inside the same modal shell (dialog role, backdrop,
Escape-to-close, `Got it`, `guideSeen` persistence all preserved). Copy lives in
one typed `SECTIONS` array. Seven sections: Quick start, Getting around, Field
properties, Common tasks, Extraction, Saving & finishing, Troubleshooting -- all
written in plain language against the exact on-screen labels. The component takes
a new `role` prop; sections marked `authorOnly` (Extraction) render only for
`role === 'author'`, so editor-tier and local-mode contractors do not see it.

The two requested emphases: Field properties frames Instructions and Format Hint
as guidance the voice AI uses to coach the user (NOT a caption on the form), with
a good-vs-poor A-Number example; Extraction stresses attaching the official
instructions PDF and explains that the extractor folds matched passages into each
field's Instructions, saving re-typing and giving the AI richer help from the
start.

Wiring in `App.tsx`: pass `role` to the guide, and surface the Help button in
local mode too (was hosted-gated) -- the editing content is identical, so local
authors benefit; the first-run auto-open stays hosted-only, so local dev startup
is unchanged. This is a decide-by-default call (reversible one-liner), noted for
the maintainer.

Doc-freshness fixes (README.md / EDITOR_GUIDE.md): corrected stale claims -- drag
reordering, undo/redo, and merge/consolidation all ship now (the docs called them
"future"/"coming soon") -- and added pointers that the in-app Help is the primary
contractor guide.

New test file `HostedGuide.test.tsx` (8 tests): section rendering, the
author-only Extraction gate (author shows / editor + local hide), section-nav
switching, the Instructions/Format-Hint framing, the instructions-PDF emphasis,
and that `Got it`/Escape close and mark the guide seen. Updated the one existing
test that encoded the old behavior (`App.hosted.test.tsx`: local mode used to
assert NO Help button; now asserts the button is present but no dialog
auto-opens).

Exit-criteria rubric (all PASS): (1) Help opens a multi-section guide, Extraction
shows for author and hides for editor/local -- verified live in a running dev
server (snapshot: 6 sections in local mode, Extraction absent) and by unit test;
(2) Instructions/Format Hint framed as AI guidance and Extraction emphasizes the
instructions PDF -- verified by live DOM eval and unit tests; (3) editor suite
green -- 671/671 (serial) locally, and the closeout prep's full run 935 passed.

Pre-PR assess: fresh-eyes adversarial loop run to NO-GAPS (final round on Opus).
No out-of-scope beads filed.

## Lessons

Nothing that generalizes to a standards doc. One local note: the in-editor tests
run under jsdom via a node_modules junction from the main repo, and the Windows
forks pool intermittently reports "Timeout starting forks runner" under parallel
load -- these are pool-startup flakes, not assertion failures; a serial run
(`--no-file-parallelism`) gives the clean 671/671. Consistent with the existing
memory that Windows forks-pool startup on a junctioned node_modules is flaky.

## Doc freshness

The doc-freshness gate flagged many STALE docs, but ALL of them track
backend/voice/auth files (`docs/components/voice-ai.md`,
`docs/standards/stateless-architecture.md`, `docs/components/auth.md`, etc.) that
this branch did not touch -- they were stale before this work and are out of
scope here. This branch's changes are confined to `schema-editor/`, which has no
doc-freshness tracker entry. Updated README.md and EDITOR_GUIDE.md directly (the
two contractor-facing editor docs) for the stale drag-reorder/undo/merge claims
and the in-app-Help pointer; no `*Last updated:*`-stamped tier-1/2 doc tracks the
schema-editor surface, so no stamp bump applied.

## Files touched

- `schema-editor/src/components/HostedGuide.tsx` -- rewritten into a sectioned,
  tier-aware help panel (STEPS -> SECTIONS, section rail, `role` prop).
- `schema-editor/src/components/HostedGuide.test.tsx` -- new; 8 tests.
- `schema-editor/src/App.tsx` -- pass `role` to the guide; show Help in local mode.
- `schema-editor/src/App.hosted.test.tsx` -- update the local-mode Help assertion.
- `schema-editor/README.md` -- fix stale claims; point at in-app Help.
- `schema-editor/EDITOR_GUIDE.md` -- fix stale keyboard/consolidation claims; add
  in-app-Help pointer.
- `docs/journal/entries/2026-07-09-bd-3ioz-in-app-guided-help.md` -- this entry.
