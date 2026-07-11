---
date: 2026-07-11
bead: polyglot-pdf-s9xh
title: "PLAN: continuous-DTI law-of-the-land audit epic (secretary + validator fully supported, all surfaces aligned)"
sprint: 11
tags: [doctrine]
---

## Trigger

Maintainer direction (2026-07-11): run a final audit/cleanup so continuous-DTI
-- with the secretary (ask_secretary) and the validator -- is the ONLY supported
path, aligned across every surface. Bead polyglot-pdf-s9xh carried the action-
plan skeleton from the 2026-07-11 handoff; this session ran /plan-epic on it.

## What shipped

The sprint-11 plan (docs/sprint_11_continuous-dti-law_plan.md), maintainer-
approved, plus the filed bead tree: epic polyglot-pdf-fc7t with 8 children --
7872 (flip defaults, FIRST), p5h2 (retire get_field_value, subsumes lt9z),
whid (validator-loop journal map), oiok (validator->switch_to_field rail, the
marquee), wt6w (async-validator planning gate), 4l7p (UI sweep, subsumes 944q),
55jg (legacy deletion, LAST, gated on siblings + demo test-drive, NOT on wt6w),
ft47 (docs alignment, after deletion). Ordering edges wired via bd_safe.py
dep-add; epic metadata carries plan + sprint pointers.

Planning research was a 3-agent Explore fan-out (flags/residue, recall+
validator loop, UI/docs/tests), all findings file:line-verified. Key ground
truth that shaped the plan: only deploy-demo.sh enables continuous mode (code
defaults say section-reset); get_field_value is section-1-pinned in continuous
mode while legacy SI prose still steers models to it; the validator's
section_complete trigger never fires in continuous mode (net collapsed to one
form_complete pass) and no wiring exists from a conflict verdict to
switch_to_field; VoiceOverlayMobile has no continuous gating at all; the
harness --arm section-reset consumes backend switch_to_section + the legacy-SI
renderer directly, so those survive deletion as documented harness-only
internals.

Both decision points the bead demanded were resolved and approved: D1 RETIRE
get_field_value (fallback: widen-lookup revert per lt9z option a); D2 BUILD the
correction rail prompt-level in _compose_validator_steer (no client-side
auto-navigation). Named limitation accepted: end-of-form-only validator net in
continuous mode until wt6w ships page-end triggers.

A peer-review pass on the draft plan produced five tightenings, all adopted:
criterion 3 scoped to form_complete explicitly; C2 exit criteria made
grep-checkable; getFieldBySpokenName fate resolved at planning (delete -- sole
production caller is the deleted handler); C7 gained a continuous-reconnect
exit criterion; the C5 non-dependency of C7 made explicit.

Fresh-eyes triage: see the PR record (docs-only change; fresh-eyes NO-GAPS is
the review record per the Step-5.6 gate).

## Lessons

- The "delete the legacy path" instinct needs a consumer inventory first: the
  measurement harness's baseline arm keeps two backend internals
  (switch_to_section, the legacy-SI renderer) alive after the production path
  dies. Deletion beads should name what they deliberately KEEP.
- A navigation tool and a recall tool can subsume a third: switch_to_field's
  ack already returns the current value, which together with ask_secretary
  covers everything get_field_value did -- retiring beats fixing a tool twice.

## Doc freshness

New: docs/sprint_11_continuous-dti-law_plan.md; docs/INDEX.md active-sprints
row added. Tier-2 docs deliberately NOT bumped here -- their continuous-DTI
staleness is the epic's own C8 bead (ft47), which lands after the deletion so
docs state post-deletion truth. closeout_prep's stale-doc warnings
(si-reduction, stateless-architecture, terminology, testing,
validation-delegation, voice-and-vad, technical_guide) all track source files
this docs-only branch did not touch -- pre-existing, reviewed and left.

## Files touched

- docs/sprint_11_continuous-dti-law_plan.md (new)
- docs/INDEX.md (active-sprints row)
- docs/journal/entries/2026-07-11-bd-s9xh-continuous-dti-law-plan.md (this)
- Beads (dolt, not git): epic fc7t + children p5h2/oiok/4l7p/55jg/ft47 created;
  7872/whid/wt6w re-parented; ordering edges wired; s9xh closed by this PR.
