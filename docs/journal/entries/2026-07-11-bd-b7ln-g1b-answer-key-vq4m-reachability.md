---
date: 2026-07-11
bead: polyglot-pdf-b7ln
title: "G1b answer key: two Part-5 fields re-graded after vq4m unhid them (interpreter language now filled; representative name NA on persona grounds)"
tags: [testing]
---

## Trigger

bd polyglot-pdf-vq4m fixed the frontend renderer so a `show_if` against a
checkbox-GROUP (array) trigger actually matches. The G1b clean-corpus answer key
(`backend/scripts/g1b_answer_key.py`, bd wf3q) had marked two I-90 Part-5 fields
NA with the EXPLICIT rationale that the array-match bug kept them permanently
hidden, so a real client could never send them. Post-vq4m that rationale is
stale.

## What changed after re-deriving on persona grounds

The two fields are gated on `p5_checkbox1a` (a checkbox group) via the `includes`
operator -- which vq4m fixed:

- **p5_line1b_language** -- `show_if includes` the INTERPRETER-read slug. The
  persona (Linh Nguyen, read to in Vietnamese by interpreter Maria Garcia)
  selects exactly that slug, so the field is now SHOWN. Re-graded from NA to
  **"Vietnamese"** (the interpreter's language). The corpus now sends 73 filled +
  59 NA (was 72 + 60).
- **p5_line2_nameofrepresentative** -- `show_if includes` the PREPARER-statement
  slug, which the interpreter-path persona does NOT select. So it stays hidden ->
  **NA**, but on PERSONA grounds now, not the old array-bug rationale.

Purged the stale "never-matching array `equals` / always hidden (bd vq4m)"
rationale from: the PERSONA docstring, the inline ANSWER_KEY comment, and
NA_REASONS. Also removed the same now-false "same never-matching array equals as
bd vq4m" clause from the three p4 accommodation fields' NA_REASONS -- those stay
NA on their PRIMARY gate (`p4_checkbox1 = No`), which is untouched; only the
stale secondary clause citing the fixed bug was removed.

## Verification

- `test_g1b_answer_key_coherence.py::test_p5_certification_matches_who_filled_the_form`
  updated honestly: it had asserted BOTH dependents NA + absent from the payload;
  now asserts p5_line1b_language == "Vietnamese" and present, p5_line2 still NA +
  absent. All 15 coherence tests pass; the answer-key validator passes
  (132 fields = 73 filled + 59 NA).
- Full backend suite green (1010 passed, 2 skipped).
- Exit-criterion grep: no "never" / "always hidden" vq4m rationale remains for the
  two p5 fields (the one surviving "always hidden" is in a NEGATED "not 'always
  hidden'" clause describing the corrected state).

## Note on the measurement re-run

The bead also asks to re-run the G1b accuracy MEASUREMENT so the numbers reflect
the corrected reachability. The answer-key/corpus generation is deterministic and
is fixed + tested here; the accuracy measurement against the live small model
(`probe_g1c_tuning.py`) needs a live-LLM run and will pick up the corrected corpus
on its next execution -- it is not a code gate and did not run in this session.
