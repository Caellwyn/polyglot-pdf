---
date: 2026-07-12
bead: polyglot-pdf-wt6w
title: "PLAN: decoupled async validator (page-end queue) -- sprint-12 epic filed"
sprint: 11
tags: [doctrine]
---

## Trigger

Sprint-11 epic polyglot-pdf-fc7t child C5 (the async-validator planning gate).
The maintainer directed (2026-07-10) that the validator stop blocking the voice
flow and surface findings at PAGE END; the oiok correction rail (shipped this
sprint) made the "act on a finding" half real, unblocking this planning pass.

## What shipped

The maintainer-approved SPEAR plan (docs/sprint_12_async-validator_plan.md) and
the sprint-12 build epic polyglot-pdf-09da with six children:
- W1 (xbl2) async backend: validation off the WS receive loop (create_task +
  immediate ack), per-window fail-open, batch dedupe by field-id set.
- W2 (kxkw) page-end trigger + overlapping window builder (20/10) + persisted
  high-water marks.
- W3 (pr3i) validatorFindingsQueue + page-end drain -> the shipped oiok steer
  composer (blocked on W1+W2).
- W4 (ny4s) re-arm steered markers on value change (the maintainer's PR-#413
  question, now a design change: a correction re-validates, a
  confirmed-intentional pair never re-flags).
- W5 (g0w1) pro-pass far-pair recall measurement (gated ~$0.30-0.50, runs
  first).
- W6 (gbus) conditional pro-pass wiring at form_complete (after W5 GO only;
  blocked on W5+W3).
Deps: W1,W2->W3; W5,W3->W6. W4 and W5 parallelizable.

Planning research (Explore) established the load-bearing ground truth that
shaped the design: in continuous mode NO page/section-advance event exists
(the section display is frozen, Preview stacks all pages) -- so the page-end
trigger is a pdf_position.page transition detected on the next-field seam, not
an existing section event. Sections are page-ALIGNED but finer than pages
(I-90: 28 sections / 7 pages). The client owns all state, so the findings queue
is a new persisted SchemaFormState key following the completedSections
serialization pattern; the oiok composer is trigger-agnostic so it drops in
unchanged.

The maintainer approved the plan verbatim ("approved"), which per the plan's
own "open item" also approves the W5 measurement spend and the W4 re-arm
lifecycle change.

## Lessons

- A "surface findings at page end" directive assumed a page-boundary event
  that does not exist in the shipped continuous mode -- the plan had to invent
  the trigger (page-number transition on the next-field path). Research the
  event before scoping the feature that fires on it.
- A shipped, trigger-agnostic mechanism (the oiok steer composer) makes a
  later "change WHEN it fires" epic dramatically smaller -- the correction
  half is already done and reused unchanged.

## Doc freshness

New: docs/sprint_12_async-validator_plan.md; docs/INDEX.md active-sprints row
added. No tier-2 doc bumped here (the plan is forward-looking; W1/W3/W4 will
touch validation-delegation.md when they land).

## Files touched

- docs/sprint_12_async-validator_plan.md (new)
- docs/INDEX.md (active-sprints row)
- docs/journal/entries/2026-07-12-bd-wt6w-async-validator-plan.md (this)
- Beads (dolt): epic 09da + children xbl2/kxkw/pr3i/ny4s/g0w1/gbus created,
  deps wired, plan pointer set; wt6w closed.
