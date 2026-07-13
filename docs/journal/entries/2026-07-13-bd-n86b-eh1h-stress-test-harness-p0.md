---
date: 2026-07-13
beads: [polyglot-pdf-n86b, polyglot-pdf-eh1h]
epic: polyglot-pdf-00pt
tags: [harness, testing, performance]
---

# Full-system stress-test harness (P0): i90-full plan + scenario events + all-in ledger

Epic `polyglot-pdf-00pt` (maintainer-approved plan, 2026-07-13): measure the
ASSEMBLED continuous-DTI + secretary + validator system on full I-90 passes --
cost, latency, accuracy, error-identification P/R, reactivity -- for a
quantified baseline and investor-grade numbers. This entry records P0 (the
harness build, no live spend). The live series E0-E6 is `polyglot-pdf-0cyu`,
gated on sprint-12 W2/W3/W4 landing.

## What shipped

- **`scripts/spikes/full_form_script.py`** -- generates the `--schema
  i90-full` plan from `backend/scripts/g1b_answer_key.py` (Linh Thi Nguyen
  persona): 113 spoken questions = 67 answered + 46 visible declines; 8
  copy_from/signature fields auto-applied; 11 gate-hidden fields never asked.
  show_if evaluation mirrors the frontend evaluator's operator semantics.
  Build-time guards (answer-key validation, override option-vocab check,
  show_if ordering invariant, the driver's expected-canon drift guard) all
  abort before any live spend. Phrasing is language-parameterized (E6 Spanish
  arm = a template table + fixture synth, not a rewrite).
- **`scripts/spikes/scenario_events.py`** -- event steps (recall /
  navigate_back / skip / plant / per-step path override), the E2/E3 scripts
  (planted contradictions incl. the p5/p6 language far pair), the E4
  reactivity micro-suite, and pure scorers: validator P/R against planted
  groups (precision counts plant-ATTRIBUTABLE flags -- a plant's knock-on
  genuine conflicts are correct behavior, only zero-plant-contact flags are
  false positives), latency percentiles, and fill-failure classification
  (missing / format / transcription / wrong-field / mismatch / spurious --
  each mode has a different fix).
- **`measure_form_session_costs.py` extensions** (extend-don't-fork; the 11
  pinned CSV columns + every historical arm unchanged, dry-run pinned):
  FakeClient skip/switch/steered/shown seams mirroring the shipped client;
  real `TextAIGemini` wiring (model pinned `gemini-2.5-flash-lite`) +
  `full_schema` at start_session; a NEW info-level log-tap whitelist (the
  pre-existing tap was warning+ only) with contextvar caller tagging; the
  text-cost ledger (dated flash-lite rates) making the headline a true
  all-in dollar; `ValidationSeam` (the W2/W3 client stand-in, explicitly
  RECONCILE-BEFORE-E1 against the landed `webFormConnection.ts` -- W2 in
  flight on bd kxkw, cadence revised page-agnostic bd c3uo); bounded steer
  windows driving the correction rail; GoAway hardening (drain validator
  tasks + detached secretary delivers pre-reconnect, count drops, record
  downtime); per-run `<base>.summary.json` with the full headline schema.
- **`tests/test_stress_harness_units.py`** -- 17 offline tests incl. two
  full dry-run loops through the REAL FormFillingService with a stub
  adapter that emulates the model via the production DTI empty-field-id
  coercion path.

## Found along the way (beads filed)

- The g1b answer key is stale vs the current kit: 13-digit USCIS account
  number (kit pattern is exactly 12) and the reason-for-card radio's gate
  changed from commuter-only to `in [LPR, commuter]` (visible for the
  persona; her lost-card reason should be selected). Harness carries
  overrides; bug bead filed for the key itself.
- `p6_line6a_signature` carries a phone validation pattern in the kit
  (extraction copy bug); bead filed.
- A production-faithful full pass must voice-DECLINE ~46 visible
  not-applicable fields (19 preparer + 20 additional-info among them) --
  a real UX cost the E-runs will now quantify (candidate improvement:
  block-level "does not apply" skip).

## Doc freshness

`check_doc_freshness.py` flagged `docs/standards/voice-and-vad.md` and
`docs/technical_guide.md` stale against backend files this branch did NOT
touch (this PR changes only `scripts/spikes/`, `tests/`, fixtures, and this
entry) -- pre-existing staleness, left for the branch that touched those
surfaces.

## Numbers for the series (measured baseline, not new spend)

Committed 30-34-q continuous happy runs: $0.57-0.74 (~$0.02/question,
window-bounded near-linear) => full-form ~113 questions + events ~ $2.3/run
happy, ~$3 unhappy-heavy. Approved series ceiling: ~$42 (Standard tier +
Spanish arm).
