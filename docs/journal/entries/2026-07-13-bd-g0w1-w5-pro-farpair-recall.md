---
date: 2026-07-13
bead: polyglot-pdf-g0w1
title: "W5: gemini-2.5-pro whole-form far-pair recall = 1.000 (GO for the gated pro pass)"
tags: [extractor, performance, testing]
---

## Trigger

Sprint-12 child W5 of the async-validator epic (polyglot-pdf-09da). The epic's
maintainer-preferred design for catching cross-page ("far pair") contradictions --
a fact stated one way in Part 1 and contradicted in a Part 8 free-text box -- is
ONE whole-form pro-tier validator pass at `form_complete`. But that pass was
UNMEASURED: the prior 6cfu.5 chunk-size run showed even gemini-2.5-flash caught
only 0.50 of far pairs at whole-form scale (flash-lite 0.33). W5 is the GATED-spend
measurement that answers "does gemini-2.5-pro clear the far-pair bar?" BEFORE the
wiring bead (W6, polyglot-pdf-gbus) does any work -- a GO/NO-GO gate.

## What shipped

**A findings doc + committed run data establishing 2.5-pro whole-form far-pair
recall = 1.000, verdict GO.** `scripts/spikes/w5_pro_farpair_findings.md` with the
method, the per-tier far-pair comparison, the bounded-thinking cost breakdown, and
the GO verdict; run artifacts `scripts/spikes/data/g1b_bakeoff_20260713T141057.csv`
(+ `.meta.json`).

**Result:** gemini-2.5-pro caught 6/6 far pairs (recall 1.000) at whole-form
(132-field) scale, including all 3 `duration_year` semantic cases (flash-lite 0/3,
flash 1/3) -- the only 2.5-tier model measured that catches the far/semantic
classes whole-form. Overall recall 1.000 (27/27), latency p50 5.95s. Total sweep
cost $0.3924 / 42 calls (~$0.0093/call), inside the epic's approved $0.30-0.50.

**Precision caveat carried to W6:** whole-form precision is 0.750 (9 of 15 clean
cases false-flagged), concentrated on the Part 5/6 preparer-and-interpreter
certification block and bracketed-repeat name fields. Recall is solved; W6 must add
an anti-over-flag prompt and re-measure precision before the pass ships as the sole
end-of-form report. This is a scope condition on the GO, not a blocker (over-flag
is the safe failure direction for a defense-in-depth layer, and it is promptable --
the same fix class 08zv/g1c applied to lift flash-lite precision 0.77->0.96).

**Instrument extension:** extended the 6cfu.5 chunk-size instrument
`backend/scripts/probe_g1b_model_size_bakeoff.py` rather than writing a parallel
script (experimentation-skill Gate 1: reuse the validated instrument). Added a
`gemini-2.5-pro` arm with its text rates ($1.25/M in, $10.00/M out), a per-model
BOUNDED `THINKING_BUDGET` (512) wired into the text `generate_content` config, a
per-model call-timeout override (120s), separate `thoughts_token_count` capture
with a `think_med` matrix column, and thinking-tokens-at-output-rate in `_cost`.
The baseline arms are unchanged (no thinking_config -> API default), so they stay
byte-for-byte comparable to the 6cfu.5 run. The offline `g1b_analyze.py` distance
bucketer gave far(21+) recall for free (additive CSV column; no analyzer change).

**Gate discipline (experimentation skill):** Gate 1 prior-work audit confirmed
2.5-pro had never been an arm in any probe (the question was open); the baseline to
beat and the instrument to extend were both identified. Gate 2 cost estimate was
built from the authoritative 2.5-pro pricing page + real size-132 token counts from
the 6cfu.5 CSV, with the thinking line called out separately; a single cheap pilot
call ground-truthed it (measured 317 thinking tok under the 512 budget) before the
full 42-call sweep. Size 132 only -- far pairs are 0 at sizes 20/40 (verified), so
whole-form answers the question completely at 42 calls, not 107.

**No out-of-scope work deferred.** The precision fix is W6's job (already the next
bead); a larger hard-case corpus and a second validated form (z2l9) are standing
follow-ups from the 0zp3/6cfu.5 lineage, not newly surfaced here.

Fresh-eyes (Step 5.5): Sonnet round found 1 gap -- the GO's cross-model framing
("pro is the only 2.5-family model that clears the bar") compared pro's
bounded-thinking run against the 6cfu.5 flash baseline, which ran under Vertex's
UNCONTROLLED default dynamic thinking, an uncontrolled-vs-controlled pairing the
doc called "apples-to-apples." ADOPTED: amended the findings doc (headline,
comparison table, Honesty/limits) to mark the flash/lite baseline as
dynamic-thinking and state the GO rests on pro's OWN 1.000, not the cross-model
gap. The reviewer's controlled-flash-re-measurement follow-up is filed as bd
polyglot-pdf-hy5k (out of scope for W5's own criterion; its disclosure half is
satisfied by this amendment, its re-measurement half remains). The reviewer
independently recomputed every number in the doc from the committed CSV and all
matched (recall 27/27, far 6/6, precision 0.750, cost $0.3924). One low-confidence
non-blocker (meta.json's hardcoded "bead":"polyglot-pdf-0zp3", pre-existing, not
introduced here) noted and left. Final clearing round on Opus: the Opus round re-verified every number from the CSV
(all matched) and found the disclosure fix INCOMPLETE -- the terminal Verdict
paragraph still carried the uncaveated "only 2.5-tier model that clears the bar"
framing, plus a cost-share slip (thinking is 46% of per-call cost, not the stated
40%). Both fixed (Verdict now leads with pro's own 1.000 and hedges the cross-model
gap; 40%->46%); the re-spawned Opus round then cleared <OPUS_FE_CLEAR_PLACEHOLDER>.
Opus outer review (Step 5.6): <OUTER_REVIEW_PLACEHOLDER -- fill at closeout>.

## Lessons

**2.5-pro cannot disable thinking; the cost guard is a BOUNDED budget, not budget=0.**
Unlike 2.5-flash (budget=0 turns thinking off), 2.5-pro's thinking_budget range is
128..32768 and budget=0 is rejected (ai.google.dev/gemini-api/docs/thinking); the
default is dynamic (-1), which is what dominated a prior Vertex bill. Any 2.5-pro
probe/production path MUST set a bounded positive budget and account for thinking at
the OUTPUT rate as its own cost line. This generalizes the existing
`vertex-flash-thinking-dominates-probe-cost` lesson to the pro tier (where "just set
0" does not work). Recorded to bd remember.

## Doc freshness

The `closeout_prep.py` freshness checker flagged a large set of `docs/standards/*`
and `docs/technical_guide.md` as stale against `backend/` files touched by OTHER
recent branches (config.py, live_ai_gemini.py, websocket_routes.py, etc., dated
2026-07-12/13). NONE of those files were touched by THIS branch -- W5 touches only
`backend/scripts/probe_g1b_model_size_bakeoff.py` (a spike instrument, not covered
by any standards doc's `Tracks:` globs) plus `scripts/spikes/` artifacts. Per the
closeout rule ("if a stale doc tracks files your branch did NOT touch, leave it --
it was already stale before you"), these are pre-existing staleness from prior
branches, left untouched and noted here. No doc bump is warranted for this spike.

## Files touched

- `backend/scripts/probe_g1b_model_size_bakeoff.py` -- added the gemini-2.5-pro arm,
  bounded THINKING_BUDGET + per-model timeout override wired into the text config,
  separate think_tok capture + think_med column, thinking-at-output-rate cost.
- `scripts/spikes/w5_pro_farpair_findings.md` -- the W5 findings doc (method,
  per-tier far-pair recall, cost/thinking breakdown, GO verdict).
- `scripts/spikes/data/g1b_bakeoff_20260713T141057.csv` + `.meta.json` -- run data.
- this journal entry.
