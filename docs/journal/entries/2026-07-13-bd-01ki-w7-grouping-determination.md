---
date: 2026-07-13
bead: polyglot-pdf-01ki
title: "Determination: the extractor already groups w7's 6d/6e (both hint arms) -- no ungrouping defect; the hint refines TYPE, not group-vs-split, and is a non-deterministic suggestion"
tags: [extractor, form-kits]
---

## Trigger

Maintainer observation at the 6cfu.1 checkpoint (2026-07-10): w7's printed
"Other Information" block had ~18 fillable items but the kit carried 22 fields,
with the 6d document-type checkboxes (Passport / Driver's license / USCIS /
Other) and the 6e No/Yes pair looking like separate checkbox fields rather than
consolidated groups. This bead asked whether the extraction grouping pass should
have merged them.

**Maintainer reframe (2026-07-13):** the checked-in forms are EXAMPLES for the
extractor, not production data -- so any fix belongs in the EXTRACTOR, not in a
per-form kit patch. The deliverable is a determination.

## Determination: no ungrouping defect -- the extractor groups 6d/6e reliably

**1. The current w7 kit has 6d/6e grouped.** `id_doc_type` is a `radio` with 4
options mapping `c1_11[0..3]`; `previously_received_itin` is a `radio` with 2
options mapping `c1_12[0..1]`. "Other Information" is 21 fields.

**2. The deterministic miner detects these families.**
`scripts/bakeoff/group_candidates.find_group_candidates` on the w7 AcroForm dump
returns 6 candidate families including `c1_11[0..3]` (4-widget, row-aligned = 6d),
`c1_12[0..1]` (= 6e), `c1_10` (gender), `c1_1` (application type). So the LLM
pass receives a group hint for exactly these families.

**3. The A/B fixtures show the LLM groups 6d/6e EVEN WITHOUT the hint** (this
corrects an earlier draft of this entry that misread the fixtures).
`backend/tests/fixtures/w7_candidates_{on,off}_draft.json` are RAW pre-repair
LLM drafts. Both group 6d and 6e:

| | 6d (`c1_11[0..3]`) | 6e (`c1_12[0..1]`) | draft schema_valid (as recorded) |
|---|---|---|---|
| hint OFF | grouped, 4-option field typed bare `checkbox` (`identification_documents`) | grouped, 2-opt radio | true (arm-time) |
| hint ON  | grouped, 4-opt **radio** (`identification_document_type`) | grouped, 2-opt radio | **false** |

So 6d is NEVER left as separate checkboxes in these runs -- the LLM consolidates
the family from the printed labels regardless of the hint. The hint's effect on
6d is a **type refinement**: hint-OFF produced a single 4-OPTION field but typed
it bare `checkbox` (a v2 `checkbox` is a standalone boolean -- options are
FORBIDDEN -- so that shape is actually INVALID under today's v2 model; it
predates the checkbox-options strictness, which is why the arm recorded
`schema_valid:true` then but fails re-validation now); hint-ON produced the
correct `radio` (single-select). Either way the family is consolidated, not
split -- there is no "6d ungrouped" defect for the extractor to fix. (Both draft
arms are pre-repair; `_repair_schema` normalizes the type downstream.)

**4. The reason-a..h boxes (`c1_2..c1_9`) are the case where behaviour differs,
and the hint arguably HURT here.** Hint-OFF keeps them as independent boxes
(valid); hint-ON collapsed them into one 8-option field whose option values all
duplicated to '1' (a lint ERROR, part of why the ON draft is
`schema_valid:false`). Whether the eight reasons are one single-select question
or eight independent "check all that apply" boxes is a semantic label read that
is the LLM's call; the current kit models them as separate checkboxes. Out of
scope for the 6d/6e question this bead raised.

## Honest caveat (the maintainer's robustness lens)

This is NOT a hard guarantee. The group-candidates hint is a SUGGESTION to a
stochastic LLM, and the deterministic backstop `_complete_grouped_families`
(extract_form.py:436-437) only COMPLETES a family the LLM already partially
grouped (1 owner, 0 < claimed < all) -- it SKIPS a family with 0 owners
("deterministic merge is out of scope") and never MERGES fully-split checkboxes.
That skip is a deliberate, documented choice (extract_form.py:310-317, bd
polyglot-pdf-w0eq): radio-vs-multi-checkbox-vs-split is a semantic read only the
LLM can make; an earlier mechanical widget-type override wrongly converted 16
legitimate i-90 radios and was removed. The draft-stage `schema_valid:false` on
the hint-ON arm is repaired downstream (`_repair_schema`/`_lint_schema` run after
the draft), so it is not a shipped-schema claim -- but it does show the hint can
push the LLM toward an over-eager consolidation that the pipeline then has to
clean up.

## Conclusion

For the specific 6d/6e concern this bead raised: **no extractor change is
warranted** -- the LLM groups both families reliably in the observed runs (with
and without the hint), the miner surfaces them, and the current w7 example is
correctly grouped. The residual questions are semantic LLM calls (6d's
radio-vs-checkbox_group type; the eight-reason single-vs-multi), not a mechanical
grouping gap.

What this determination does NOT claim: that grouping is deterministically
guaranteed. It is not -- the hint is a suggestion and the net can't rescue a
fully-split family. If the maintainer wants extractor ROBUSTNESS pinned (not just
"correct on these runs"), the right follow-up is an EXTRACTION-EVAL/TEST that
asserts 6d/6e (and similar radio families) consolidate on a fresh w7 run, rather
than any deterministic-merge code. Filing that decision to the maintainer rather
than presuming it (see bead comment); no kit change either way (already correct
post-#401).

## Files touched

- this journal entry (the determination; no code change)
