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

Key results (CORRECTED -- a Codex review rebuilt the corpus and the conclusions
CHANGED; see the "Codex review" note and the lesson below):
- **Local contradictions: every model is good.** zip/state, city/state, adjacent
  dates -- all caught at form scale.
- **Far-apart, cross-section contradictions DEGRADE recall for the cheap text
  models.** On genuine cross-section cases (a Part-1 field vs a Part-8 textarea
  ~85-96 fields apart), 2.5-flash catches 3/6, 2.5-flash-lite 2/5, 3.1-flash-lite
  4/6; the voice model and 3-flash-preview catch 6/6, 3.5-flash 5/6. On the
  `duration_year` class ("lived in US 20 years" vs a 2020 admission date),
  2.5-flash AND 2.5-flash-lite catch 0/3. This is the REVERSE of the first
  (flawed-corpus) pass, which had concluded "distance does not degrade recall."
- **Precision is the cheap models' weakness** (~0.55-0.73; they over-flag valid
  city/state pairs and the mailing-vs-physical addresses), worsening at 132.
- **Recommendation: a GENUINE per-boundary model split** -- 2.5-flash-lite (or
  3.1-flash-lite) for the per-section LOCAL check, and 3.5-flash for the
  end-of-form CROSS-SECTION pass (the cheap models, AND 2.5-flash, miss the
  far/duration cases the end-of-form pass exists to catch). The first pass wrongly
  said no split was needed.

**Live API evaluated and REJECTED.** The maintainer asked to test the actual voice
model (`gemini-2.5-flash-native-audio`) as the checker. It cannot emit TEXT
(modality 1007), so it was driven text-in over a Live session in TOOL-CALLING mode
(reports the verdict through a `report_conflicts` tool call). On the corrected
corpus its recall is 0.938/1.000/0.963 (20/40/132) and -- notably -- it is one of
only two models that catch ALL the far/duration cross-section cases (6/6 far,
3/3 duration_year), BETTER than 2.5-flash on the hard cases. But at 6-18s
per-call latency plus the Live-session tech debt (holding sockets across
minutes-long idle gaps past the ~30-60s timeout, history-token buildup,
dropped-socket handling), a plain HTTP call to 3.5-flash gets comparable hard-case
recall without that overhead. So it stays REJECTED as the checker -- but its
strong hard-case recall is a data point if "voice model does double-duty" is ever
revisited.

**3.5-flash measured** (132 only): recall 0.963, precision 0.634, far 5/6,
duration_year 2/3 -- it is the simplest (plain HTTP) model that HOLDS UP on the
cross-section cases the cheap tier misses, so it is the RECOMMENDED end-of-form
model. It is the priciest text model ($0.008/call uncached), but context caching
(untested) would cut that and the absolute per-form cost is tiny.

**Follow-up filed: bd polyglot-pdf-08zv** (G1c) -- optimize 2.5-flash end-of-form
LATENCY (context caching + payload trim) and 2.5-flash-lite per-page PRECISION
(anti-hedging prompt + few-shot, the FPs are concentrated and promptable). Code
Execution for deterministic lookups noted there as a deferred precision lever.

**Fresh-eyes (Sonnet, 5 rounds to convergence, all findings adopted):** round 1
caught a real measurement bug -- the voice model's tool call TRUNCATES field ids
(`p1_line6e` for `p1_line6e_state`), so exact-set scoring wrongly counted 3 cases
as misses and reported voice recall as 0.875/0.957 at sizes 20/40. Fixed with
prefix-tolerant `_detected` + a re-score pass in `g1b_merge.py` (corrects the data
without re-calling the API); true voice recall is 1.000 at all sizes. That fix
rippled: rounds 2-4 chased the derived staleness it exposed -- the accuracy cells,
then the LATENCY cells (recomputed every matrix cell from MERGED.csv, now with a
programmatic 0-mismatch check), then an error-counting inconsistency (an API
timeout is "no measurement", not a miss -- made `g1b_analyze.py` exclude errored
rows to match the matrix), then prose-vs-table rounding. Round 5 reached the last
prose inconsistency (the headline precision range understated the measured floor;
unified to ~0.62-0.80). Also adopted across rounds: voice + 3.5-flash added to the
distance/class tables (EC2); disclosed precision is CASE-LEVEL (the user-visible
spurious-pair rate is higher); corrected the TX-in-radio corpus-artifact impact
(a ~8-pt precision swing at 132 that flips the lite ordering); fixed a stale
docstring + a self-contradictory voice-run meta. The corpus filler fix + the
case-vs-group precision question were folded into the follow-up bead (08zv). No
out-of-scope beads filed by fresh-eyes. (The 3-round ceiling was exceeded with
maintainer authorization -- each round's gaps were a descending cascade from the
one root fix, not new defects, and convergence was the goal.)

**Codex review (post-PR, 10 findings, ALL adopted -- and it CHANGED the
conclusions).** Where 7 fresh-eyes rounds verified INTERNAL CONSISTENCY (does the
doc match the data), Codex questioned MEASUREMENT VALIDITY (is the data measuring
what it claims). It found: the far-distance cases paired the applicant's state with
a DIFFERENT person's ZIP (not a contradiction); `cross_date` duplicated
`admission_dob`; the advertised `duration_year` class was never generated; size-132
actually transmitted ~84 fields (empty clusters dropped); the TX-in-radio filler
artifact; the scorer counted partial-group flags as catches (inflating
far-distance recall); the probe counted timeouts as misses; the offline merge
imported the API SDK; the analyze "latest CSV" glob picked the stale MERGED file.
Fixed all (4 code-only + 5 corpus changes), rebuilt the corpus, and RE-RAN the live
sweep -- which reversed the headline finding (distance DOES degrade recall; the
cheap models miss duration_year entirely). Maintainer chose full rigor (fix
everything + re-run) over caveat-and-defer.

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
- **A corpus filler bug masquerades as a model weakness.** Precision numbers were
  repeatedly inflated by filler bugs (a substring persona that put 'TX' into a
  Yes/No checkbox AND into a 'city and state' field; a base physical address that
  contradicted injected mailing addresses; a substring-match that put the residence
  city into the birth-city field) -- the model was CORRECTLY flagging my bad test
  data. Read the model's `reason` text on false positives before trusting a
  precision number. Type-gate filler by field type so a non-option value can never
  land in a constrained field.
- **Internal-consistency review and measurement-validity review are DIFFERENT, and
  both are needed.** Seven adversarial fresh-eyes rounds drove the doc to perfect
  internal consistency (the matrix reproduced from the CSV with 0 mismatches) and
  STILL missed that the corpus itself was measuring the wrong thing -- unsound
  far-distance cases, a duplicated class, a never-generated class, a payload that
  was 84 fields not 132. Codex caught those by asking "is this measuring what it
  claims?" not "does the doc match the data?". For a MEASUREMENT artifact, schedule
  a validity pass (does each case test what its label says? does the payload match
  the advertised size? is every claimed class actually generated?) separate from
  the consistency pass -- a self-consistent report can still be confidently wrong.
- **A methodology fix can REVERSE the conclusion -- re-run, do not patch.** The
  corpus fixes changed the measured recall enough to flip the headline (far
  distance went from "no effect" to "the cheap models miss half"). When a fix
  changes the INPUT to a measurement, the old output is void; re-run the sweep, do
  not try to reason about what the number "would have been".
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
