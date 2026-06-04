---
date: 2026-06-04
bead: polyglot-pdf-3yf
title: "closeout_finish.py now commits+pushes its telemetry row so it isn't orphaned in the worktree"
tags: [harness, testing]
---

## Trigger

`bd polyglot-pdf-3yf`, filed this session after the maintainer reported that
`.beads/experiment_state.json` + `docs/journal/harness_ledger.jsonl` were
perpetually dirty at session-archive time and worried telemetry was being lost.

## What shipped

**Root cause.** `closeout_finish.py`'s step plan wrote the ledger row *after* the
closeout commit AND after the push: commit (staged closeout work) -> rebase ->
push -> open PR -> [request review] -> **telemetry (writes the 2 files)**. No step
committed those two files, so every closeout left its own row uncommitted. It
survived only by accident -- swept into a later fix-commit, or hand-committed
out-of-band (the historical `chore(harness): PR #NN telemetry row` commits). The
last row of a branch (a `--skip-review` PR with no further commits, or the final
run on a branch) was reliably orphaned and lost on archive.

**Fix.** Added a `commit_push_telemetry` step right after `telemetry`. It:

- guards on the real dirty state of exactly the two tool-owned paths
  (`docs/journal/harness_ledger.jsonl`, `.beads/experiment_state.json`) and
  no-ops when clean (ledger GAP / `--no-bump` / nothing to do);
- commits them BY EXPLICIT PATH (`git commit -- <paths>`, never `git add`) with a
  `chore(harness): PR #<n> telemetry row (recorded by closeout_finish.py)` message,
  then pushes;
- is WARN-ONLY like the telemetry write itself: a commit/push failure annotates
  `out["telemetry"]` (`COMMIT-FAILED` / `PUSH-FAILED`) but never changes the exit
  code -- the PR is already open, so a telemetry hiccup must not fail the closeout;
- is NOT in the `--close-only` plan (that path writes no row, by hrn.15);
- self-heals a pre-existing dirty telemetry file, since `git commit -- <paths>`
  sweeps up whatever is dirty at those paths.

This is the ONE place the script commits its own files; the "never `git add` the
orchestrator's content" rule is preserved (explicit-path commit of the tool's own
bookkeeping, never `git add -A`). Module docstring + `--dry-run` plan line updated.

**Tests (5 new, in `tests/test_closeout_finish.py`):** commits+pushes dirty
telemetry files (asserts both paths in one commit, PR# in message, push follows);
no-op when clean; every git call is `git -C <WT>` and none use `add`; push-failure
is warn-only; `--close-only` never touches telemetry. 29 pass (was 24).

**Also rode this PR:** the orphaned `4ok` telemetry row from PR #67. My earlier
hand-rescue commit landed AFTER #67 was already merged (merged at head `a8957bf`,
which didn't include the rescue), so that row never reached `dev` -- verified
missing from `origin/dev`'s ledger. It is bundled here so it finally lands. (A
small irony: the very orphaning this PR fixes also bit the manual rescue, because
the rescue raced the merge.)

## Fresh-eyes triage

(to be completed at closeout)

## Doc freshness

closeout_prep flagged the usual backend-tracked tier-2/standards docs as stale,
but this branch touches only `scripts/closeout_finish.py` + its test (+ the two
telemetry data files). None of the flagged docs track those, so none was bumped
(Step-2 rule: stale doc tracking files this branch didn't touch is left as-is).
The branch's apparent extra files in `origin/dev..HEAD` before the pre-push rebase
were an artifact of a stale base (the branch was cut before PR #68 merged); the
rebase absorbed #68 cleanly and the diff is the 4 expected files.

## Files touched

- `scripts/closeout_finish.py` -- `commit_push_telemetry` step + plan wiring +
  docstring.
- `tests/test_closeout_finish.py` -- `TestTelemetryCommitPush` (5 cases).
- `docs/journal/harness_ledger.jsonl` + `.beads/experiment_state.json` -- the
  rescued `4ok` row (data, not logic).
