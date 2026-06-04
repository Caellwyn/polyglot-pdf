---
date: 2026-06-04
bead: polyglot-pdf-8o4
title: "Prevent telemetry git collisions: union-merge ledger + derive counter from ledger"
tags: [harness, conventions]
---

## Trigger

PR #75 hit a merge conflict on `docs/journal/harness_ledger.jsonl` because PR #76
merged first and both had appended a closeout telemetry row. Investigating, the
collision had two distinct sources, and one was worse than a mere annoyance:
- **Ledger** (append-only JSONL): a line-level conflict in the trailing region on
  *every* parallel pair -- trivial to keep-both, but a manual rebase each time.
- **`.beads/experiment_state.json`** (whole-file counter rewrite): a **silent
  correctness bug** -- two parallel same-arm sessions both bump `baseline_A`
  N->N+1, a merge keeps only one, so the counter undercounts.

## What shipped

Two-part fix making both collision-proof:

1. **Union-merge the ledger.** New root `.gitattributes`:
   `docs/journal/harness_ledger.jsonl merge=union`. `union` is a git **built-in**
   driver (no `.git/config` registration; portable on git 2.53) -- on a conflict
   it keeps BOTH sides' appended lines, so two PRs' rows auto-merge instead of
   colliding. Proven on a synthetic parallel-append: `git merge` -> 0 conflict
   markers, both rows present.
2. **Derive the counter from the ledger.** `scripts/harness_ledger.py`:
   - New `derive_experiment_state(ledger_path)` -- a pure projection that counts
     rows by their `arm` field (`baseline_A` = #arm=="A", etc.; null/unknown count
     toward nothing). `phase` derived from the counts via the unchanged ladder.
     Missing ledger -> zeros; malformed lines skipped (reuses `_iter_records`).
   - `bump_experiment_state` -> `refresh_experiment_state(ledger_path, state_path)`:
     re-derives from the ledger (which now includes the just-appended row) and
     writes the cache. No `arm` param, no read-mutate-write -- counts can no longer
     be lost to a merge.
   - `main()` appends the row FIRST then refreshes; `--print-directive` derives on
     demand (works with the cache file absent).
   - `.beads/experiment_state.json` is now a **gitignored local cache** (added to
     `.gitignore`, `git rm --cached`'d). `closeout_finish.py`'s `_TELEMETRY_FILES`
     is ledger-only, so closeout no longer commits the counter -> its collision
     surface is gone entirely.

**Cutover identity verified:** deriving over the current 15-row ledger yields
`baseline_A=14` (14 arm="A" + 1 arm=null), exactly matching the committed counter.
No off-by-one; the gitignored file's last committed value was correct.

**Decision (noted):** kept writing the gitignored cache (vs. dropping it) -- it
preserves the `cat .beads/experiment_state.json` affordance and keeps `--no-counter`
meaningful (skip the cache write), while correctness comes from always re-deriving.
Reversible, low-consequence -- decided per the escalation doctrine.

**Fresh-eyes triage:** <!-- FRESH-EYES-PLACEHOLDER: filled at closeout -->

This PR dogfoods its own union driver: if another telemetry PR merges first, this
PR's ledger row should auto-merge cleanly instead of conflicting.

## Lessons

- **A value derived from a committed source should not itself be committed.** The
  counter was a cache masquerading as source-of-truth; committing it created a
  whole-file collision surface AND a lossy-merge bug. Deriving it from the
  append-only ledger (which union-merges safely) removes both.
- **`merge=union` is the right tool for append-only tracked files** (ledgers,
  changelogs, journals). It is a git built-in -- a one-line `.gitattributes` entry,
  fully portable, no setup. (Added to `docs/journal/TAGS.md`-tagged record here;
  worth a `bd remember`.)

## Doc freshness

- The freshness checker flagged several `docs/components/*` + `docs/standards/*` as
  STALE -- all track `backend/` files (config.py, live_ai_gemini.py,
  callback_handler.py) changed by OTHER work (the compression PRs). **This PR
  touches no backend files** (only scripts/, tests/, git config, the closeout
  skill), so per the closeout Step-2 rule they were stale before this branch and
  are left untouched.

## Files touched

- `.gitattributes` (new) -- union-merge for the ledger.
- `.gitignore` -- untrack `.beads/experiment_state.json` (+ `git rm --cached`).
- `scripts/harness_ledger.py` -- `derive_experiment_state`; `bump`->`refresh`;
  `main()` + `--print-directive` derive on demand; help/output wording.
- `scripts/closeout_finish.py` -- `_TELEMETRY_FILES` ledger-only + docstrings.
- `tests/test_harness_ledger.py` -- bump tests -> derive tests + new coverage
  (null/unknown-arm, missing ledger, malformed line, refresh-writes-cache,
  print-directive-without-cache).
- `tests/test_closeout_finish.py` -- telemetry-commit test: ledger-only, counter
  must NOT be committed.
- `.claude/skills/closeout/SKILL.md` -- Step 8.5: counter derived, not bumped.

## Out-of-scope finding (filed)

While running the full suite I found **5 pre-existing backend test failures on
`dev`** (`test_live_ai_gemini.py`, `KeyError: 'context_window_compression'`) --
verified pre-existing (they fail with this branch's changes stashed), unrelated to
telemetry, likely from the compression work. Filed as **bd polyglot-pdf-ztn (P1)**;
not fixed here. The `tests/` dir (this PR's surface) is fully green.
