---
date: 2026-08-03
bead: polyglot-pdf-41fi
title: "fix(voice): prompt-tuning bundle -- natural yes/no asks, no print-navigation cruft, long-list read-out verified"
tags: [conventions, harness, testing]
---

## Trigger

Maintainer go-ahead ("proceed with the prompt-tuning bundle... use your
live-driving skill; I'm not in a place where I can test them myself") on the
two recital-phrasing follow-ups from the bd 6bq8/s503 reviews, with the
long-list live verification folded into the same harness session: bd
polyglot-pdf-41fi (binary yes/no fields forced out of natural phrasing), bd
polyglot-pdf-c2jy (printed-form navigation inside labels recited verbatim),
and bd polyglot-pdf-bxra (live-verify the standard-list carve-out delivers
the full read-out on request).

## What shipped

- **41fi -- two-option fields are one natural question.** The render adds a
  fourth marker: a recital-side field with exactly 2 options gets
  `Options (2 -- ask ONE natural question that makes both choices clear; do
  not recite the labels as a list)`. The DTI SI's PRESENTING OPTIONS block
  gains the matching rule (plain yes/no question when the options amount to
  yes/no; either/or question otherwise), and BOTH initiating templates carry
  the same scope -- the bd 6bq8 lesson that an unqualified template directive
  beats a distant SI rule.
- **c2jy -- speak the substance, not the print/screen wording.** New SI rule:
  never read aloud a label's printed-form navigation or cross-references
  (item/line/box numbers, "(Proceed to Item 5.a)", "Skip line 6f", "see
  instructions") or screen wording ("Select Yes") -- the app navigates the
  form automatically. Framed as the ONE exception to MATCHING's
  say-as-written rule, and MATCHING's line now carries the coupling so the
  two rules cannot read as contradicting.
- **bxra -- verified live and its fixture committed.**
  `read_all_options.wav` added via `gen_fixtures.py` (the canonical
  generator). The audio is committed for future harness runs; it is NOT yet
  wired into a named harness scenario in `harness.js` -- the bead's criterion
  asked for the live verification, which this closeout performed by driving
  the fixture manually.

**Live verification (I-90, real Gemini, resume path per case):**
- `p1_checkbox4` (3 options with "(Proceed to Item Numbers 5.a. - 5.c.)"
  tails): asked as "Has your name legally changed since your Permanent
  Resident Card was issued? The options are: Yes, No, or Not Applicable if
  you never received your previous card." -- all three options' substance,
  zero navigation cruft. (c2jy criterion 1.)
- `p3_checkbox4[1]` (labels "Select No"/"Select Yes"): asked as the single
  natural question "Have you ever been in exclusion, deportation, or removal
  proceedings, or ordered removed from the United States?" (41fi criterion 1.)
- `p1_line6e_state` (50-option select): asked "What is your mailing state?
  I can read the full list for you if you'd like." and the injected "Can you
  please read me the whole list of options?" produced a complete recital --
  all 50 states present, zero missing, verified programmatically against the
  transcript. (bxra's full criterion.)

**Cost note:** the DTI SI grows 15,266 -> 16,424 chars (~8%), the price of
the two new rules; same accounting as the 6bq8 entry (per-turn text-in is
the cost lever), flagged in the merge report.

**Review outcome:** recorded in the merge ping after the pre-PR loops.

## Lessons

- The recital rule needed three refinement rounds (numeric enumerations,
  yes/no fields, print-navigation cruft) after the initial "read everything"
  directive -- each a case where the printed form's option STRUCTURE is not
  the right spoken UX. The stable shape that emerged: type decides the ask
  style (select vs group), count decides the recital form (2 / <=20 / >20),
  and a substance rule governs what part of each label is voiced. Worth
  remembering when authoring future kits: label text IS spoken UX.

## Doc freshness

- `docs/standards/si-reduction.md` -- bumped: fourth marker, the two new SI
  rules, the MATCHING coupling, and the measured SI size.
- The pre-existing stale set flagged by the freshness checker (recorded in
  the bd 6bq8 entry) is unchanged by this diff and left as-is.

## Files touched

- `backend/config.py` -- PRESENTING OPTIONS: SPEAK-THE-SUBSTANCE rule +
  two-option rule; MATCHING coupling; both initiating templates' two-option
  scope.
- `backend/services/ai_context.py` -- the n==2 natural-question marker.
- `backend/tests/unit/test_dti_si_voice_rules.py` -- kit-backed tests for
  the two named yes/no fields and the two named multi-option lists; SI prose
  pins for both new rules; template pins; updated 2-option expectations in
  the type-gate and enum tests.
- `tests/e2e/voice-harness/gen_fixtures.py` +
  `frontend/public/test-fixtures/read_all_options.wav` -- the bxra fixture.
- `docs/standards/si-reduction.md` -- freshness bump.
- `docs/journal/entries/2026-08-03-bd-41fi-prompt-tuning.md` -- this entry.
