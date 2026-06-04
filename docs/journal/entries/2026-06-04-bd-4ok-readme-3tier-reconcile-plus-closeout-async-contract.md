---
date: 2026-06-04
bead: polyglot-pdf-4ok
title: "Reconcile README with the 3-tier docs + document the closeout async-task (do-not-poll) contract"
tags: [conventions, doctrine, harness]
---

## Trigger

`bd polyglot-pdf-4ok` (a docs-reorg follow-up deferred out of `4p0`): `README.md`
still framed `planning_documents/` as canonical reading and pointed AI assistants
at files that had since been archived. Bundled with a small closeout-SKILL doc fix
that came out of the PR #64 debrief (see below) -- both pure docs, same
review-skipped class, so one PR.

## What shipped

**4ok -- README reconciliation.** Rewrote every stale pointer in `README.md` to the
live 3-tier docs:

- `:195` architecture-plan pointer -> `docs/INDEX.md` + `docs/technical_guide.md`.
- `:239` dangling `MANUAL_TESTING_GUIDE.md` -> `docs/standards/testing.md` (the
  guide file does not exist anywhere; it was a dead link, so replaced not
  re-pointed).
- `:243-249` "Planning Documents" section -> a proper 3-tier map (CLAUDE.md,
  docs/INDEX.md, docs/technical_guide.md, components/, standards/, genai_docs/,
  journal/) with a note that planning material is archived under `docs/archive/`
  and `planning_documents/archived/` and is no longer canonical.
- `:330-331` contributor workflow -> read CLAUDE.md + docs/INDEX.md first; check
  `bd ready` for the next unit of work (was "review REFACTOR_IMPLEMENTATION_PLAN
  for current phase").
- `:344` + `:361` doc-maintenance bullets -> "update the relevant tier-2 doc + add
  a journal entry" (was "update planning documents" / "update TECHNICAL_GUIDE.md").
- `:432` closing "For AI Assistants" pointer -> CLAUDE.md + docs/INDEX.md.

Verified no `planning_documents/<DOC>` / `PROJECT_CONTEXT` / `REFACTOR_*` /
`MANUAL_TESTING_GUIDE` / `TECHNICAL_GUIDE.md` references remain in README, and that
the archive locations cited actually exist.

**Closeout SKILL -- async-task contract.** Added a paragraph to the `--close-only`
documentation stating that a *hand-run* `closeout_finish.py --close-only` runs the
slow `bd dolt push`, so the harness backgrounds it and notifies on completion:
fire it and END the turn, do not `sleep`/`cat`/poll its output. This generalizes
the round-1 watch's already-stated "no polling turns" rule (Step 6.2) to *every*
backgrounded step. It closes a real gap: the SKILL documented the watcher's async
contract loudly but said nothing about hand-run `--close-only`'s, which is exactly
where the PR #64 closeout wasted ~4 turns hand-polling. (Maintainer's framing:
set the expectation at the point of invocation, in the SKILL -- the natural home
for per-script behavior -- not in a post-hoc banner or a new skill.) A matching
memory was written so the lesson is in effect immediately, not only on re-read.

## Doc freshness

closeout_prep flagged several tier-2/standards docs as stale, but **all of them
track `backend/` source files** (`callback_handler.py`, `live_ai_gemini.py`) that
this branch does NOT touch -- the staleness was introduced by the prior PR (#64)
and measured against its merge timestamps. Per the Step-2 rule ("if a stale doc
tracks files your branch did NOT touch, leave it"), no timestamps were bumped.
This branch's diff is README.md + SKILL.md only.

## Stale-bead note

`polyglot-pdf-hrn` (P1 epic, in_progress 2d) flagged again -- same separately-owned
in-flight epic as the PR #64 closeout; unrelated to this PR, left untouched.

## Files touched

- `README.md` -- 3-tier doc reconciliation.
- `.claude/skills/closeout/SKILL.md` -- `--close-only` async-task / do-not-poll
  contract.
