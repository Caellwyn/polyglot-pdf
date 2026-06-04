---
date: 2026-06-04
bead: polyglot-pdf-6hl
tags: [conventions]
---

## Trigger

`6hl`: stale retired model aliases (`gemini-live-2.5-flash-preview`,
`...native-audio-09-2025`, `...native-audio-dialog`) lingered in
`planning_documents/code_examples/live_api/*`. Picked up as non-overlapping work while
`c5t` (GoAway) was blocked by a collision with `333`. Bundles the closed-out `daa`
diagnostic artifact (see below).

## What shipped

**`6hl` -- deleted the dead vendored example dir.** The bead posed a delete-vs-freeze
decision; chose DELETE. The dir is 11 files of VENDORED upstream Google Colab snippets
(`# @param` markers), under the archived non-canonical `planning_documents/` tree
(README 4ok), and NOTHING live references it (verified: repo-wide grep for
`code_examples/live_api` outside that tree + docs returns nothing). The canonical SDK
reference is `docs/genai_docs/` (curated + current). A second, stale, unmaintained mirror
full of retired aliases is a misleading trap -- precisely the model-name confusion that
cost real time this session (the `1008` cascade strings in the compression
investigation). Per the bead, hand-patching the aliases was explicitly NOT the task
(would diverge the mirror from upstream); freezing only helps if we'd diff vs upstream,
which we don't. Reversible via git history. Siblings (`firebaseConfig.js`,
`gemini_rest_api_guides`) left untouched.

**`daa` artifact (closed measurement-only, bundled here).** `daa` (2.5-native `code=1011`
~80% report) was closed NOT-AFFECTED: `scripts/spikes/diag_native_audio_1011.py` drove 15
sustained audio turns per model and got 30/30 clean -- zero 1011 -- on BOTH
`gemini-3.1-flash-live-preview` (our default) AND
`gemini-2.5-flash-native-audio-preview-12-2025` (the implicated preview). The upstream
issue appears resolved; the bead's premise ("our default is the 2.5 preview") was also
outdated (default is 3.1). The probe rides along here so its evidence isn't orphaned in a
worktree -- `daa` closed without a PR of its own.

**Collision-guard fix (incidental, unblocked the whole repo).** Claiming any bead aborted
because `polyglot-pdf-333` (native-VAD smoke test, in_progress) had NO declared
`metadata.surfaces`, which `bd_safe.py`'s R1 guard treats as UNKNOWN -> collides with
everything. Verified `333` was an idle claim (branch == dev, no commits, no uncommitted
work) and declared its real surface
(`backend/adapters/live_ai_gemini.py`, `backend/config.py`,
`backend/routes/vad_config_routes.py`); also declared `6hl`'s surface
(`planning_documents/code_examples/live_api/`). With both sides declared, the guard
proved disjointness and the claim succeeded. This unblocks every other claim too.

## Lessons

- **An in_progress bead with no declared change-surface poisons the R1 collision guard
  for the WHOLE repo** (UNKNOWN collides with everything, both sides). Declaring surfaces
  on the offending bead -- not `--no-surface-check` overrides -- is the root-cause fix.
- **A stale vendored doc mirror is worse than no mirror.** Retired model aliases in a
  dead example tree read as authoritative and mislead; delete dead mirrors, keep one
  curated current reference (`docs/genai_docs/`).

## Doc freshness

- **Reviewed and left as-is:** all flagged docs are stale by *mtime* from dev's recent
  merges / other worktrees' backend edits -- NONE triggered by this PR (archived-file
  deletion + a spike script; no tracked doc references either). No doc references the
  deleted dir (verified pre-delete), so nothing dangles.

## Files touched

- Deleted `planning_documents/code_examples/live_api/` (11 files).
- Added `scripts/spikes/diag_native_audio_1011.py` (daa evidence probe).
- (bd metadata, not files) declared `metadata.surfaces` on `333` and `6hl`.
