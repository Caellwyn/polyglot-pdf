---
date: 2026-08-22
bead: polyglot-pdf-aqjg2
title: "docs(closeout): document the two new preconditions ATTENTION causes"
tags: [doctrine, review]
---

## Trigger

`closeout_prep.py`'s `check_preconditions()` gained two new ways to return
ATTENTION -- a branch that REVERTS files the base already has, and a
detector failure reported as UNVERIFIED. Neither appeared in
`.claude/skills/closeout/SKILL.md`'s "Step 0 detail -- Preconditions",
which enumerated exactly two causes (DIRTY, no-commits-ahead) and
prescribed a response for each.

The control flow was never at risk: `closeout-runner.md` stops on ANY
prep ATTENTION and returns the TODO verbatim. So an orchestrator could not
blunder past it -- it would simply find no matching entry in the reference
it had just been pointed into.

## What shipped

Both causes added to the triage list, each with its own response, taken
from the real summary strings and branch logic in `closeout_prep.py`
(:296-313) and cross-checked against CLAUDE.md scar #3 (:124-138).

## Lessons

**The responses are opposite, which is what made the omission worth
fixing rather than tolerable.** A REVERTS fire can mean two different
things that look identical from outside:

- the squash-to-a-branch-name trap -> STOP, redo the squash from the
  merge-base;
- a deliberate revert or deletion -> confirm intent and proceed.

CLAUDE.md already carried the caveat ("confirm intent, do not read a fire
as proof of the trap"), but only in CLAUDE.md and a Python comment -- not
in the document an orchestrator consults *at the moment it is triaging*.
Guidance that lives one hop away from the decision point is guidance that
does not exist when it matters.

The UNVERIFIED case needs a third response again, and it is the one most
likely to be misread: the detector FAILED, so it is fail-closed, not a
pass. Silence there is the exact failure the check exists to eliminate.

**A doc gap can be real even when the control flow is safe.** It was
tempting to treat "the runner cannot proceed past it" as making this
cosmetic. It doesn't: the cost is not a broken pipeline, it is an
orchestrator reaching for a reference that comes up empty and then
improvising -- with two plausible responses available and no way to tell
which is right.

## Scoping note

`.claude/agents/closeout-runner.md` was deliberately NOT changed. It stops
on any ATTENTION and defers triage by design; adding per-cause guidance
would duplicate the reference into a file that intentionally does not
triage. The reviewer independently verified that behavior and agreed
leaving it alone was correct.

## Doc freshness

- `.claude/skills/closeout/SKILL.md` -- Step-0 triage list extended from
  two causes to four. No stamp (skill file). Conventions clean.

## Files touched

- `.claude/skills/closeout/SKILL.md` -- two new triage entries
