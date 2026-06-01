---
date: 2026-06-01
bead: polyglot-pdf-5ys
title: "copilot_watch.py: report MERGED as a distinct terminal state"
tags: [conventions]
---

## Trigger

Maintainer request (2026-06-01): streamline the closeout loop so the orchestrator
doesn't need a separate `gh pr view` to learn a PR was merged. The maintainer
noticed (twice — PRs #41 and #42) that I narrated "ready for your merge" without
re-checking state, and that the merge event already shows in the PR timeline the
watcher polls. So: have `copilot_watch.py` report the merge directly.

## What shipped

`scripts/copilot_watch.py`:

- `_pr_is_closed(repo, pr) -> bool` → `_pr_closed_state(repo, pr)` returning
  `"merged"` / `"closed"` / `None`, using the PR object's `merged_at`/`merged` fields
  (already in the `repos/{}/pulls/{}` payload it fetched).
- **Merge is checked FIRST** in each poll iteration, before `_timeline_state` — a
  merge makes the review verdict moot, and (the key fix) a merge was otherwise being
  *masked* by Copilot's own terminal state (`copilot_work_finished` → CLEAN) or a
  lingering approval comment. Emits a new `RESULT: MERGED` terminal state (exit 0).
- closed-without-merge still emits `CLEAN`; docstring terminal-states list +
  `_EXIT_CODES` updated.

**Agent semantics:** `RESULT: MERGED` ⇒ work is already merged → skip the
maintainer-merge ping, go straight to bead-close (no `gh pr view` needed).

### Verified live

Ran the watcher against the two already-merged PRs: **#42 → `RESULT: MERGED`** and
**#41 → `RESULT: MERGED`** (exit 0). Before this change both returned CLEAN/COMMENTS —
the first attempt (merge-check gated on `state is None`) was masked by Copilot's
finished-state; moving the check to the top of the loop fixed it.

### Review triage (PR #<TBD>)

_To be filled after round-1 triage._

## Lessons

The merge-check had to run **first**, not as a fallback: the watcher's timeline-state
classifier (`reviewed`/`finished`) and the issue-comment classifier both short-circuit
the loop, so a merge gated behind "Copilot produced no verdict" never fired when
Copilot had left any review/comment (which is almost always). Order matters in a
priority-of-terminal-states poll loop — the most decisive outcome (merged) goes at the
top. Also a personal process lesson reinforcing
[[verify-claims-against-code-not-brief]]: I'd been narrating PR outcomes from the last
value I fetched rather than re-querying — this change removes the need to, but the
habit (re-check state at each cycle close) still applies for anything the watcher
doesn't report. The script is not unit-tested, so it was verified by running it
against real merged PRs.

## Doc freshness

- No tier-1/tier-2 doc tracks `scripts/copilot_watch.py`, so this change triggers no
  doc updates. (The closeout/review-flow doctrine docs describe the watcher's role but
  not its exit-state contract.)
- All docs flagged STALE by the checker track `live_ai_gemini.py` / `config.py` /
  `main.py` / schema-forms TS — files this branch did NOT touch (pre-existing from the
  merged p1t fix + earlier work). Left as-is.

## Files touched

- `scripts/copilot_watch.py` — `_pr_closed_state` + merge-first poll check + `MERGED` terminal state.
- `docs/journal/entries/2026-06-01-bd-5ys-copilot-watch-py-report-merged-as-a-distinct.md` — this entry.
