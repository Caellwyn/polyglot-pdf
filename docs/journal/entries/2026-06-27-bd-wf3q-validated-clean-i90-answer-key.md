---
date: 2026-06-27
bead: polyglot-pdf-wf3q
title: "G1b precision corpus: a hand-validated coherent I-90 answer key replaces the naive filler"
tags: [performance, testing, postmortem]
---

## Trigger

The G1b bake-off (bd 0zp3, PR #242) measures a contradiction checker's PRECISION
on "clean" full-I-90 form states. Three rounds of Codex review found the clean
states kept containing UNLABELED contradictions from the naive per-field filler in
`g1b_corpus.py` -- `option[0]` of the name-change radio asserts "Yes, my name
changed" while the name fields are identical; the English-self-cert checkbox is
checked while a Part 6 interpreter is populated; state pickers got full names
("California") instead of the schema's option values ("CA"). A good checker
correctly flagged this bad test data and the corpus scored it as a false positive:
86 of 128 clean-case false positives touched a contaminating field, so the
precision numbers were not trustworthy. (RECALL was always trustworthy -- it is
measured on deliberately-injected, correctly-labeled contradictions, which filler
noise cannot change.)

Root cause: a real I-90 is ~132 densely INTERRELATED fields where many controls are
semantic assertions that constrain other fields (name-change Yes/No gates the
previous-name fields; the English/interpreter certification gates which of Parts
6/7 are coherent; LPR-vs-commuter gates the port-of-entry field). Naive per-field
filling cannot be coherent because it ignores those gates, and per-field
whack-a-mole did not converge across three review rounds.

## What shipped

The maintainer-specified fix (bd wf3q): do, by hand with big-picture reasoning,
exactly the validation task we ask the small gemini model to do -- read the schema
(field semantics + option LABELS + conditional logic) together, build ONE coherent
persona, answer every field into a dictionary, mark conditional/NA fields
explicitly, self-review to zero unlabeled contradictions, then mutate.

- **`backend/scripts/g1b_answer_key.py`** (new) -- the hand-validated clean answer
  key. `ANSWER_KEY` maps every one of the 132 field_ids to a coherent value (or
  `None` for a conditional-hidden / inapplicable field, with the gating reason in
  `NA_REASON`). The persona is Linh Thi Nguyen, a Vietnamese-born LPR replacing a
  lost green card, Houston TX, name unchanged, served by a Vietnamese interpreter
  and a non-attorney preparer. 90 fields filled + 42 NA. The module's docstring
  records the persona and the coherence invariants the self-review enforced. A
  `validate_answer_key()` function mechanically guards coverage, valid option
  values, copy-field equality, and NA bookkeeping (it guards against drift; it does
  not replace the semantic hand-review that produced the values).

- **`backend/scripts/g1b_corpus.py`** (rewritten) -- `build_corpus(size)` now
  builds the clean base from `ANSWER_KEY` (omitting NA fields, as production omits
  empties) instead of the deleted `_filler` / `_first_option_value` /
  `_PERSONA` / `_CLUSTER_FILL` machinery. The `Case` dataclass and the
  `build_corpus(size)` signature are unchanged, so the probe
  (`probe_g1b_model_size_bakeoff.py`) and the offline re-scorer (`g1b_merge.py`)
  consume it drop-in, and the `s{size}_{class}_{i}` case_ids stay stable for
  re-score. Contradiction cases start from the validated base and inject ONE
  labeled contradiction; clean cases apply coherent address variants (US,
  foreign, US-territory, dual-address) as precision traps. Injections into
  normally-NA fields (foreign province, Part 8 free-text) are ADDED at their
  document-order slot so distance stays meaningful.

- **`backend/tests/unit/test_g1b_answer_key_coherence.py`** (new) -- turns the
  wf3q hand-audit into a durable regression guard: the answer key validates; every
  schema field is covered exactly once; the named artifact classes
  (state/country, province/state, name-change-Yes-without-previous-name,
  English-self-cert-with-interpreter, copy-field inequality, full state names) are
  absent across all cases at all sizes; the corpus shape is stable (far-apart
  classes only at size 132, one expected group per contradiction case).

**Pre-PR adversarial fresh-eyes (Sonnet) returned NO-GAPS against all three exit
criteria.** Its two real nits were adopted inline: (a) every address-injection case
(zip_state / state_country / province_us) now also overrides the mailing CITY to one
coherent with the injected state, so each injected case carries EXACTLY ONE labeled
contradiction -- previously the base city "Houston" stayed while the state changed,
leaving a second, unlabeled city-vs-state contradiction (harmless to the scorer,
which never scores labeled cases as false positives, but a latent coherence issue);
(b) a misleading "physical == territory address" comment + a 0.91->0.90 rounding
fix in the findings banner. It filed bd polyglot-pdf-fwp6 (dead `seed_offset`
param) as out-of-scope; that one-line removal was trivially safe (no g1b caller
passed it), so it was FOLDED INTO this PR and fwp6 closed -- this PR closes wf3q +
fwp6. The earlier-filed bd zi2s (schema show_if/controls_fields discrepancy) stays
deferred (a real schema reconciliation, genuinely out of scope).

## Validation

- `validate_answer_key()`: 0 problems (132 fields = 90 filled + 42 NA).
- Adversarial semantic audit (by hand + scripted scans): 0 unlabeled
  state/country/province artifacts in clean cases; 0 name-change or
  English/interpreter artifacts across ALL cases; copy-fields equal sources.
- `probe ... --dry-run` (perfect oracle): recall = precision = 1.000 across the
  matrix -- the labels are internally consistent and the scorer consumes the new
  corpus cleanly.
- New coherence tests: 9 passed.
- Stdlib-only import verified (the offline re-scorer runs without google.genai).

## A schema discrepancy found (filed, not fixed)

`p2_checkbox1.controls_fields` unlocks the Reason-for-New-Card field
(`p2_checkbox2[5]`) for option [0] (plain LPR) AND option [1] (commuter), but
`p2_checkbox2[5].show_if` narrows visibility to option [1] only. Every I-90
applicant must give a reason, so a plain LPR should see it -- the `show_if` is too
narrow. The answer key follows the authoritative `controls_fields` map and
documents the call inline; reconciling the schema is out of scope for wf3q -> filed
**bd polyglot-pdf-zi2s**.

## Result / next

The clean-corpus PRECISION re-measure (exit criterion 3) was run on the two cheap
text models the recall finding points at (2.5-flash-lite per-section, 2.5-flash
end-of-form), all three sizes, ~360 live calls, ~$0.09. On the final CLEAN corpus
(run `g1b_bakeoff_20260627T115647`, after BOTH the fresh-eyes injection-city fix
AND the Codex round-1 fixes -- option-label resolution, the p2/p5 coherence fixes):

| model | size | recall | precision |
|-------|-----:|-------:|----------:|
| 2.5-flash-lite | 20 | 1.000 | 0.800 |
| 2.5-flash-lite | 40 | 0.952 | 0.909 |
| 2.5-flash-lite | 132 | 0.852 | 0.793 |
| 2.5-flash | 20 | 1.000 | 1.000 |
| 2.5-flash | 40 | 1.000 | 1.000 |
| 2.5-flash | 132 | 0.963 | 1.000 |

These precision numbers are now TRUSTWORTHY: every remaining false positive is a
GENUINE checker over-flag on a COHERENT payload, not a corpus artifact. The
breakdown by clean-trap type (both models, all sizes) proves it:

- `clean_baseline` (the full validated persona, the densest trap): **0/6 flagged**;
  `clean_dual` (mailing + physical, both valid but different): **0/8 flagged**.
- `clean_us` (coherent US addresses): 1/30. After Codex's option-label fix, there
  are **ZERO** lone `p1_line8_male` / `p5_checkbox1a` over-flags -- those were
  corpus artifacts (the checker saw the opaque token `P1_Line8_female[0]` with no
  meaning), not model noise as the earlier writeup wrongly claimed. 2.5-flash is now
  precision 1.000 at every size.
- The remaining false positives concentrate exactly where a cheap checker is
  genuinely weak: foreign addresses 8/24, US territories 3/18 -- all coherent
  payloads the prompt explicitly says NOT to flag (a foreign
  province+postal+country with no US state; Puerto Rico / Guam / USVI ZIPs).
  2.5-flash-lite drives all of these.

So the precision story is now real: 2.5-flash is FULLY precise (1.000 at all sizes)
and the weakness is the lite model on hard foreign/territory coherent addresses.

## Codex outer review (PR #253)

Codex round 1 returned 5 P1 findings -- all genuine, all adopted (none were nits):

1. **state_country / province_us left the base US ZIP (77027)** alongside the
   injected foreign country / province -> a SECOND unlabeled contradiction. Fixed:
   the ZIP is cleared in those cases (each injected case carries exactly one
   labeled contradiction; a new test asserts it).
2. **p2_checkbox2[5] (reason for new card) was filled, but the production renderer
   show_if-gates it to commuter status** and hides + rejects it for a plain LPR --
   a payload a real client could not send. Fixed: marked NA (the schema
   discrepancy itself stays tracked in bd zi2s).
3. **The payload sent raw option tokens** (`P1_Line8_female[0]`, `P5_Checkbox1b[0]`)
   with no meaning, so the checker spuriously flagged coherent non-first options --
   the lone-field FPs were corpus artifacts, not model noise. Fixed: option values
   are resolved to their human LABELS in the payload (opaque tokens only; legible
   short codes like state `TX` are left as-is per the bead's abbreviation rule).
   This is what drove 2.5-flash precision to 1.000.
4. **Part 7 preparer was fully populated but the applicant did not certify the
   preparer statement** (p5_checkbox1a) -- an unlabeled contradiction in a clean
   case. Fixed: p5_checkbox1a is a checkbox GROUP and now selects BOTH the
   interpreter and preparer statements, and the representative-name field is filled.
5. **Adding physical-address mutations made the s20_clean_us_* cases skip** (physical
   out of the size-20 window), dropping their stable case ids and leaving
   g1b_merge.py to retain stale rows from old run files. Fixed two ways: the
   physical mutations are now BEST-EFFORT (mailing-only is coherent at size 20, so
   the ids survive), AND a `corpus_fingerprint()` is stamped on every run row +
   meta so g1b_merge.py merges ONLY same-corpus runs (it now excludes
   pre-fingerprint / other-corpus rows, reporting the dropped count).

Six new regression tests lock these in. The clean numbers above are the post-fix
re-measure. This unblocks bd 08zv (G1c precision/latency tuning), which must
not trust any precision result until the corpus is clean. The recall finding (bd
0zp3 / PR #242) was already shippable; the precision numbers are now trustworthy
too.

## Doc freshness

This branch touches only the G1b bake-off harness (`backend/scripts/g1b_*.py`),
its new test, `scripts/spikes/`, and `docs/journal/`. No tier-1/tier-2 doc has a
`**Tracks:**` glob that covers any of those paths, so there is no surface doc to
bump for this change.

The closeout doc-freshness check flagged ~22 STALE tier-2 docs, but every one of
them tracks runtime code from OTHER sprints (`backend/routes/`,
`backend/adapters/`, `backend/config.py`, `backend/services/`, `backend/models/`,
`frontend/`) that this branch did NOT touch -- they were stale before this work.
Per the doc-maintenance rule (only bump a stale doc whose tracked files THIS
branch changed), they are left as-is and noted here.

Beads housekeeping flagged 3 stale `in_progress` beads (`polyglot-pdf-hrn`,
`jf6w`, `ue5s`) -- none are this PR's bead, none are orphans, and they are the
maintainer's own long-running epics/tasks, so they are left untouched (transitioning
another owner's active work is out of scope for this closeout).

## Files touched

- `backend/scripts/g1b_answer_key.py` (new) -- the validated clean answer key +
  `validate_answer_key()`.
- `backend/scripts/g1b_corpus.py` (rewritten) -- `build_corpus(size)` on the answer
  key; same `Case`/signature/case_id contract.
- `backend/tests/unit/test_g1b_answer_key_coherence.py` (new) -- 9 coherence guards.
- `scripts/spikes/g1b_bakeoff_findings.md` -- a precision-update banner pointing at
  the clean-corpus re-measure (bd 0zp3's findings doc; pointer only).
- `scripts/spikes/data/g1b_bakeoff_20260627T115647.{csv,meta.json}` (new) -- the
  clean-corpus precision re-measure run (final corpus, post fresh-eyes + Codex
  round-1 fixes; carries the corpus_fp column).
- `backend/scripts/probe_g1b_model_size_bakeoff.py` -- stamps corpus_fp on every
  row + meta (so g1b_merge merges only same-corpus runs).
- `backend/scripts/g1b_merge.py` -- filters to the current corpus_fp; excludes
  pre-fingerprint / other-corpus rows with a reported count.
- `docs/journal/entries/2026-06-27-bd-wf3q-...md` (this entry).
