---
date: 2026-06-19
bead: polyglot-pdf-0zp3
title: "G1b: model x form-size bake-off for the out-of-band B checker"
tags: [performance, postmortem, testing]
---

## Trigger

Follow-up to G1 (jnjj.5), which reframed Pillar B of the SI-reduction epic from
"replace the in-system-instruction ADDRESS-CONSISTENCY check with a cheap model"
to "add an OUT-OF-BAND end-of-section + end-of-form contradiction checker" (the
in-SI check stays; the new checker is one safety layer among many -- per-field
read-back, verbal section verification, human translator review). G1 measured one
model on tiny 3-5 field clusters; the open questions for the actual checker were:
WHICH cheap model, and does accuracy survive a realistic page- or form-sized
payload? This bead ran a model x form-size bake-off measuring speed, cost, AND
accuracy, with the maintainer steering scope mid-flight.

## What shipped

A 6-model x 3-size measurement matrix (575 cells), a clear two-tier
recommendation, and a hard rejection of the Live-API-as-checker idea.

**The matrix** (`scripts/spikes/g1b_bakeoff_findings.md`, data in
`scripts/spikes/data/g1b_bakeoff_MERGED.csv`): 4 text models +
the voice model + 3.5-flash, over 20/40/132-field synthetic-but-real-I-90 form
states with contradictions injected at varied DISTANCES (adjacent vs
cross-section, up to 83 fields apart).

Key results:
- **Recall is near-solved at form scale** (all models >=0.96 at every size) --
  REVERSING G1's worry; more context HELPED. The G1 state_country blind spot is
  gone. Distance does NOT degrade recall (cross-section contradictions caught as
  reliably as adjacent ones).
- **Precision is the differentiator.** Flash-lite tiers ~0.65-0.80 (they
  over-flag valid US city/state pairs -- "New York is not in New York"), 2.5-flash
  ~0.82-0.89, all at negligible cost. The flash-lites are sub-second; the bigger
  models 8-25s.
- **Recommendation: two-tier UNARY HTTP.** 2.5-flash-lite per page (<1s), 2.5-flash
  end-of-form (best precision 0.89). NOT a per-boundary-different-model split (the
  bead anticipated maybe needing it; the data says no).

**Live API evaluated and REJECTED.** The maintainer asked to test the actual voice
model (`gemini-2.5-flash-native-audio`) as the checker. It cannot emit TEXT
(modality 1007), so it was driven text-in over a Live session in TOOL-CALLING mode
(reports the verdict through a `report_conflicts` tool call). It works (recall
1.000 at every size after prefix-tolerant re-scoring, precision ~0.76-0.80) but at
6-9s cold-per-call latency -- no
accuracy win over 2.5-flash, and the Live-session tech debt (holding sockets
across minutes-long idle gaps past the ~30-60s idle timeout, history-token
buildup, dropped-socket handling) is not worth it for discrete batch validation a
plain HTTP call does better. Maintainer's call: stop forcing a stateful streaming
pipeline into a unary job.

**3.5-flash measured** (132 only): recall 1.000, precision 0.86, but ~4x costlier
than 2.5-flash at full rate with no precision gain. Not preferred (caveat: context
caching, not modeled here, could shift its cost case -- noted for the follow-up).

**Follow-up filed: bd polyglot-pdf-08zv** (G1c) -- optimize 2.5-flash end-of-form
LATENCY (context caching + payload trim) and 2.5-flash-lite per-page PRECISION
(anti-hedging prompt + few-shot, the FPs are concentrated and promptable). Code
Execution for deterministic lookups noted there as a deferred precision lever.

**Fresh-eyes (Sonnet, 1 round, GAPS-FOUND (2) + 3 supporting findings -- all
adopted):** caught a real measurement bug -- the voice model's tool call TRUNCATES
field ids (`p1_line6e` for `p1_line6e_state`), so exact-set scoring wrongly counted
3 cases as misses and reported voice recall as 0.875/0.957 at sizes 20/40. Fixed
with prefix-tolerant `_detected` + a re-score pass in `g1b_merge.py` (corrects the
data without re-calling the API); true voice recall is 1.000 at all sizes. Also
adopted: added the voice + 3.5-flash rows to the distance/class tables (EC2);
disclosed that precision is CASE-LEVEL (the user-visible spurious-pair rate is
higher); corrected the "marginal" claim about the TX-in-radio corpus artifact (it's
a 12-pt precision swing at 132 that flips the lite ordering); fixed a stale
docstring. The corpus filler artifact + the case-vs-group precision question were
folded into the follow-up bead (08zv). Adopt 5 / reject 0 / defer 0; no
out-of-scope beads filed by fresh-eyes.

## Lessons

- **A measurement harness needs a per-call TIMEOUT, or one hung call freezes the
  whole run.** The first full sweep hung ~2 hours on a single stalled
  `generate_content` call -- the retry logic only caught EXCEPTIONS, but a call
  that hangs open is not an exception. Fixed with `asyncio.wait_for`. Long runs
  also need INCREMENTAL checkpointing (the per-size-only checkpoint lost a
  near-complete cell when straggler retries kept the process alive past the size)
  and bounded concurrency tuned per payload size (high concurrency on the big
  132-field payloads triggered a rate-limit -> timeout spiral).
- **The native-audio 1011 "internal error" is a malformed-TOOL-DECLARATION
  symptom, not endpoint flakiness** (maintainer). A deeply nested
  array-of-objects tool schema made the voice model 1011 on 7/8 calls; a FLAT tool
  (an array of ';'-joined strings) fixed it to 0 errors. Confirmed by isolation:
  no-tools calls succeeded 8/8 while the nested-tool calls failed. When a Live
  model 1011s, suspect the tool schema first.
- **A corpus filler bug masquerades as a model weakness.** Early precision numbers
  were inflated by two corpus bugs (a base persona physical address that
  contradicted injected mailing addresses; a substring-match that put the
  residence city into the birth-city field) -- the model was CORRECTLY flagging my
  bad test data. Read the model's `reason` text on false positives before trusting
  a precision number.
- **Don't dismiss a model from a too-narrow list filter.** I initially reported
  `3.5-flash` as nonexistent; it was in the model list, my grep was too narrow.
  The maintainer caught it. Verify a model id by calling it, not by filtering a
  list.

## Doc freshness

- No tier-1/tier-2 doc tracks this bead's files (the bake-off scripts under
  `backend/scripts/` + data/findings under `scripts/spikes/`). The findings doc +
  this journal entry are the artifacts. `docs/standards/validation-delegation.md`
  (the frozen B contract) is unaffected -- this bead measures model choice, it does
  not change the verdict/payload/steering contracts.
- The closeout freshness checker flagged ~18 docs stale, but ALL are stale against
  source files updated 2026-06-16/17 by OTHER branches (config.py,
  callback_handler.py, websocket_routes.py, etc.) -- this branch touched NONE of
  them. Left as-is per the doc-freshness rule (stale-before-this-branch).
- No CLAUDE.md changes.

## Files touched

- `backend/scripts/g1b_corpus.py` -- NEW: full-size labeled corpus over real I-90
  fields, contradictions at varied distances.
- `backend/scripts/probe_g1b_model_size_bakeoff.py` -- NEW: the bake-off probe
  (text `generate_content` path + Live tool-calling path; timeout, retry,
  concurrency, checkpointing).
- `backend/scripts/g1b_analyze.py` -- NEW: per-distance + per-class + per-size
  breakdown from the CSV.
- `backend/scripts/g1b_merge.py` -- NEW: merge/dedup the per-run CSVs (the sweep
  ran in pieces) preferring non-errored rows.
- `scripts/spikes/g1b_bakeoff_findings.md` -- NEW: the matrix, FP analysis,
  Live-API rejection, recommendation.
- `scripts/spikes/data/g1b_bakeoff_MERGED.csv` + the canonical per-run CSVs/metas
  -- NEW: the measurement data (575 cells).
- `docs/journal/telemetry/2026-06-17T...json` -- a stray jnjj.5 telemetry row that
  slipped from PR #234, committed here (append-only, no conflict).
