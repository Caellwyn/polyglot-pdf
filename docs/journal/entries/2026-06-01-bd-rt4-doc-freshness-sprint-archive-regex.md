---
date: 2026-06-01
bead: polyglot-pdf-rt4
title: "Fix doc-freshness sprint-archive regex + land the first tier-1 sprint plan"
tags: [conventions, testing, review]
---

## Trigger

A fresh-eyes review of the agentic coding harness (token-burn + autonomy) produced
an approved plan; the maintainer asked to store it as the first tier-1 sprint plan
and beadify it. While wiring the plan into `docs/INDEX.md`, the doc-freshness checker
kept warning, surfacing two long-standing, recurring issues the maintainer wanted
resolved rather than re-surfaced every closeout: `polyglot-pdf-rt4` (sprint-archive
regex never matches the real INDEX row) and two perpetually-"stale" docs.

## What shipped

- **Sprint-1 plan as a tier-1-tracked doc.** `docs/sprint_1_harness-tuning_plan.md`
  (token-burn + bounded-autonomy plan), linked from INDEX's "Active sprint plans"
  row. Beadified into two epics: `polyglot-pdf-hrn` (near-term #1 telemetry, #2
  fresh-eyes tiering, #3 bounded loop, #4 closeout_prep, #5 risk-rating, #5b
  conflict-resolution) and `polyglot-pdf-h2r` (roadmap R1–R4), with the A/B arms and
  whole roadmap gated on `hrn.1` (telemetry). Change-surfaces stored in bead
  `--metadata` (the R1 collision-guard field, used early).

- **rt4 fix.** `ACTIVE_PLAN_ROW_RE` anchored on the literal `sprint_<N>_<slug>_plan.md`
  being the *first* table cell, but the real INDEX row leads with a `**Active sprint
  plans**` label cell. Relaxed the anchor to match the literal in any cell (still
  requiring a real cell boundary). Hardened the test fixture (`_make_index`) to the
  real two-cell layout — the old fixture's first-cell shape is exactly why CI stayed
  green while the checker warned in production — and added a regression test that runs
  the parser against the live `docs/INDEX.md`.

- **Two stale docs, content-verified then fixed** (not blind-restamped):
  - `schema-forms.md` flagged on a *real* change — `conditional_logic` added as a
    legacy alias of `conditional_behavior`, honored by `FieldRenderer`. Documented the
    alias, then restamped.
  - `confirmation-and-audit.md` flagged on *noise* — a pricing-comment edit in the
    churny `config.py`. Dropped `config.py` from its `**Tracks:**` (noting the
    `confirm_field` declaration's location inline; a real tool change travels with the
    still-tracked `callback_handler.py`), then restamped.

- **Deferred:** `polyglot-pdf-9pe` — closeout/freshness scripts resolve `$R` to the
  MAIN repo and audit it, not the worktree branch under review.

- **Drive-by green-the-suite:** closeout's test step surfaced a pre-existing red test
  on `dev` — `tests/test_copilot_watch.py::test_exit_code_map` asserted a 4-key
  `_EXIT_CODES` dict, but the code added a 5th terminal state `MERGED: 0` (which the
  closeout doc already lists). Untouched by this branch; fixed the stale assertion +
  parametrize here so the PR ships on a green suite.

Fresh-eyes triage: see the PR body.

## Lessons

- **A test fixture that doesn't mirror the real artifact's shape gives false
  confidence.** rt4's regex had passing tests while warning in production because the
  fixture put the anchor token where the regex expected it — a place the real INDEX
  never used. When a regex/parser targets a specific real file, pin a regression test
  against that real file, not only synthetic fixtures.
- **Verify a "stale" doc against its triggering commit before restamping.** One of the
  two was genuinely out of date (needed a content line); the other was pure
  whole-file-tracking noise (needed a narrower `**Tracks:**`). A blind date-bump would
  have ossified the first one's inaccuracy.
- **Closeout's own scripts audit `main`, not the worktree** (see `polyglot-pdf-9pe`).
  Recorded as agent scar tissue; validate branch doc edits by running the worktree's
  own copy of the checker with cwd = worktree.

## Doc freshness

- `docs/components/schema-forms.md` — content update (conditional_logic alias) + restamp 2026-06-01.
- `docs/standards/confirmation-and-audit.md` — narrowed `**Tracks:**` (dropped config.py) + restamp 2026-06-01.
- `docs/INDEX.md` — added the active sprint-plan link (no `**Tracks:**`, not freshness-checked).
- `docs/sprint_1_harness-tuning_plan.md` — new.
- No CLAUDE.md change.

## Files touched

- `docs/sprint_1_harness-tuning_plan.md` — new tier-1 sprint plan.
- `docs/INDEX.md` — link the active plan in the sprint-plans row.
- `scripts/check_doc_freshness.py` — relax `ACTIVE_PLAN_ROW_RE`.
- `tests/test_doc_freshness.py` — harden `_make_index` fixture to real layout; add live-INDEX regression test.
- `docs/components/schema-forms.md` — document conditional_logic alias; restamp.
- `docs/standards/confirmation-and-audit.md` — narrow Tracks; restamp.
- `tests/test_copilot_watch.py` — fix stale `_EXIT_CODES` assertion + parametrize to include `MERGED` (pre-existing red, unrelated to rt4).
- `docs/journal/entries/2026-06-01-bd-rt4-doc-freshness-sprint-archive-regex.md` — this entry.
