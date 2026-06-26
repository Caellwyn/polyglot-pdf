---
date: 2026-06-26
bead: polyglot-pdf-0zp3
title: "HANDOFF: G1b bake-off at Codex round 3 -- precision corpus needs a clean answer key (bd wf3q)"
tags: [performance, postmortem, harness]
---

## Where this stands (read first)

**Branch:** `claude/0zp3-model-size-bakeoff`. **PR:** #242 (OPEN, into `dev`).
**HEAD:** `19b742a0` ("round-2-corpus re-run -- conclusions STABLE").
**Bead 0zp3** (the bake-off) is NOT closed; PR #242 is NOT clean yet.
**Uncommitted:** only a stray telemetry json (`docs/journal/telemetry/2026-06-25T17-05-35Z-*.json`) -- safe to commit or ignore.

The G1b model x form-size bake-off measures, per (model x size), whether a cheap
contradiction-checker model catches injected contradictions (RECALL) and avoids
false alarms (PRECISION). Findings doc: `scripts/spikes/g1b_bakeoff_findings.md`.
Data: `scripts/spikes/data/g1b_bakeoff_MERGED.csv`. Harness:
`backend/scripts/g1b_{corpus,scoring,merge,analyze}.py` +
`probe_g1b_model_size_bakeoff.py`.

## The settled, TRUSTWORTHY result (this part is done)

**RECALL is solid and the decision is made.** Across two corpus rebuilds + two
full live re-runs, the conclusion is STABLE:

- On LOCAL contradictions (zip-vs-state, city-vs-state, adjacent dates) every model
  is near-perfect.
- On FAR-APART / cross-section contradictions -- the realistic "a fact stated in
  two different places" case -- the CHEAP text models miss a lot:
  - far-bucket recall: 2.5-flash 4/6, 2.5-flash-lite 2/5, 3.1-flash-lite 4/6.
  - `duration_year` ("lived in US 20 years" in Part 8 vs admission date 2020):
    2.5-flash-lite 0/3, 2.5-flash + 3.1-flash-lite 1/3.
  - the models that HOLD UP: 3-flash-preview (far 6/6, duration 3/3), 3.5-flash
    (5/6, 2/3), voice/native-audio (5/6, 2/3).
- **Recommendation (robust): a per-boundary model split** -- a flash-lite for the
  per-section LOCAL check, and **3.5-flash** (plain HTTP) for the end-of-form
  CROSS-SECTION pass. The original "one cheap model handles everything" was an
  artifact of a flawed first corpus. The voice/Live-API path is rejected as the
  checker (latency + tech debt) despite good hard-case recall.

RECALL is trustworthy because it is measured on DELIBERATELY-INJECTED, correctly-
labeled contradictions -- corpus filler noise cannot change it.

## The OPEN problem (why PR #242 is not clean) -- precision corpus contamination

PRECISION is NOT trustworthy. Codex has reviewed PR #242 three times (10 -> 8 -> 4
findings; each round real, none re-litigation). The residual issue, surfaced in
round 3, is that the SYNTHETIC "clean" full-I-90 forms keep containing UNLABELED
contradictions from naive per-field filler, so models correctly flag my bad test
data and it scores as a false positive. **86 of 128 clean-case false positives
touch a contaminating field.**

Codex round-3 specifics (the still-open findings on PR #242, commit 19b742a0):
1. `g1b_corpus.py` -- `option[0]` of several radio/checkbox is a SEMANTIC
   ASSERTION, not neutral: `p1_checkbox4` (name-change) defaults to "Yes" while the
   previous-name fields equal the current name; Part 5 English-self-cert is checked
   while the interpreter/preparer sections are populated. Each is an unlabeled
   contradiction.
2. `g1b_corpus.py` -- `MAIL_STATE`/`p1_line6e_state` is a `select` whose schema
   option values are ABBREVIATIONS (`CA`,`NY`); the injections use full names
   ("California"), which production enum-validation would reject -- scoring on
   impossible payloads.
3. journal entry `2026-06-19-...md:40` -- stale "Key results" numbers (still say
   3/6, 0/3 etc.) that no longer match the corrected CSV/findings. (DOC-ONLY; the
   findings doc matrix/tables ARE correct, verified 0-mismatch vs CSV; only this
   journal "Key results" bullet block and possibly a couple of journal lines lag.)

This is the SAME class of problem hit three times: a real I-90 is ~132 densely
INTERRELATED fields where many controls constrain others, so naive filler keeps
manufacturing inconsistencies. Per-field whack-a-mole does NOT converge.

## THE PLAN (bd polyglot-pdf-wf3q) -- maintainer-specified, do this next

Do, by hand with Opus 4.8's visual + big-picture reasoning, exactly the validation
task we ask the small gemini model to do. Big-picture -> details, iterate to zero
contradictions, THEN mutate.

1. **Inject the documents into context**: the RENDERED I-90 PDF pages (visual --
   you can reason over images) AND `form-kits/i-90/schema.json`. Read them TOGETHER
   so you understand each field's semantics + the conditional/hidden logic.
2. **Create a COHERENT PERSONA**: one fictional person, coherent life history
   (origin country, immigration timeline, name history, addresses, etc.).
3. **Answer each question into a DICTIONARY**: keys = field_id (+ question text),
   values = the answer. Mark fields that are HIDDEN / NA under the form's
   conditional logic (e.g. previous-name fields only apply if name-change = Yes).
   Use SCHEMA OPTION VALUES for every control (state abbreviations, the actual
   radio/checkbox option values), never free-text labels a dropdown would reject.
4. **Review the dictionary for contradictions/omissions** -- iterate big-picture ->
   details until NONE remain. This validated dictionary IS the clean answer key
   (the "correct filled form").
5. **Create MUTANT versions** with PREDICTABLE injected errors (omissions,
   contradictions) that SPAN the bake-off's contradiction classes (zip/state,
   state/country, city/state, future-dob, admission-before-dob, far-apart
   cross_date, duration_year). These become the labeled corpus.

Deliverable: this validated clean key + labeled mutants REPLACES the
`g1b_corpus.py` filler approach. Then re-measure the bake-off PRECISION on the
clean corpus (recall will be re-confirmed too). Exit criteria are on bead wf3q.

## How to finish PR #242 (two options for whoever picks this up)

The recall finding is shippable as-is. Choose with the maintainer:

- **(A) Ship the recall finding now, fix precision later.** On PR #242: fix the
  state-abbreviation injection bug (corpus:377) so address VALIDITY holds, fix the
  stale journal "Key results" (journal:40), add an explicit "PRECISION IS
  CONTAMINATED -- see bd wf3q" caveat to the findings doc, re-trigger Codex, and
  take it to merge. The clean-corpus precision re-measure happens under wf3q.
- **(B) Hold PR #242 until wf3q lands**, then re-run with the clean corpus and ship
  one complete report. More correct, slower; PR #242 sits open meanwhile.

The maintainer leaned toward a focused "fill the form correctly" bead (wf3q) as the
real fix; they did NOT explicitly pick A vs B for PR #242 -- confirm before merging.

## Harness state (all committed, working)

The probe/scoring/merge/analyze code is in good shape after the Codex fixes
(stdlib-only scorer, full-group + bracket-disambiguated matching, model-format-
failures-scored-as-misses, end-to-end latency, error-exclusion, MERGED-glob fix,
checkpointing, per-call timeout, bounded concurrency). The probe writes a
`flagged_groups` column so a re-score can do full-group matching WITHOUT re-running.
`g1b_merge.py` dedups across run files preferring non-errored rows (this is how the
recurring Google 5xx waves on 2.5-flash-lite were recovered -- run twice, merge).
Run mechanics + lessons are in `scripts/spikes/g1b_bakeoff_findings.md` and the
main journal entry `2026-06-19-bd-0zp3-...md`.

Other open follow-up beads: **polyglot-pdf-08zv** (G1c -- 2.5-flash-lite precision
prompt tuning + 3.5-flash end-of-form latency/caching; note its recommendation was
updated to 3.5-flash). The wf3q clean-corpus work should land BEFORE trusting any
precision-tuning result from 08zv.
