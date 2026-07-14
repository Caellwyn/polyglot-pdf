# DRAFT -- series in progress

Data-only draft. Numbers below are pulled directly from the artifact
summary.json / meta.json files under `scripts/spikes/data/`. No verdict
prose yet -- that comes in a later pass once E3/E4/E6 land.

## 1. Method summary

- Harness: `measure_form_session_costs.py --schema i90-full`, real backend
  stack against **live Vertex** (not a mock), continuous DTI (dynamic tool
  injection) + context-window compression (trigger 5000 tokens / window
  3500 tokens).
- Persona: Linh Nguyen, 113 spoken questions (full I-90 walkthrough) for the
  E1/E2 runs; the E0 pilot used a 10-question slice of the same persona.
- Tool catalog: production 6-tool set (`update_form_fields`, `confirm_field`,
  `ask_secretary`, `switch_to_field`/`switch_section`, `skip_field`,
  `get_form_status`).
- Model: `gemini-live-2.5-flash-native-audio` (tier "2.5").
- All runs are **local** (harness runs against the local dev backend, not
  the deployed Cloud Run demo). Per the maintainer, local wall-clock/turn
  latency numbers **overstate** what the deployed (Cloud Run, co-located
  with Vertex) service will show -- see bd memory
  `harness-local-latency-overstates-deployed`. Treat every latency/wall-clock
  figure below as a local-harness ceiling, not a production estimate. Cost
  and accuracy/behavioral numbers are not subject to this caveat.

## 2. Per-run table

| run id (started) | phase / arm | all-in USD | voice USD | text USD | wall-clock | fill acc | failure modes (missing/format/transcr/wrong-field/mismatch/spurious) | evictions | reconnects (announced/spontaneous) | stalls | 1011s | DTI coercions | secretary calls | validator windows/steers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E0 pilot 1 -- T054615Z (pre-fix, 10q) | happy | $0.189541 | $0.189541 | $0 | 96.4 s | 7/10 (0.70) | 0/0/2/0/1/0 | 1 | 0/0 | 0 | 0 | 0 | 0 | 0/0 |
| E0 pilot 2 -- T055241Z (post-fix, 10q) | happy | $0.250448 | $0.239185 | $0.011263 | 97.5 s | 10/10 (1.00) | 0/0/0/0/0/0 | 2 | 0/0 | 0 | 0 | 0 | 10 | 0/0 |
| E1 run 1 -- T055600Z | happy | $2.425401 | $2.420659 | $0.004742 | 1015.7 s (16.9 min) | 99/113 (0.876) | 0/3/4/0/4/3 | 30 | 1/0 | 0 | 0 | 0 | 4 | 9/1 |
| E1 run 2 -- T061257Z | happy | $2.416718 | $2.415933 | $0.000785 | 965.2 s (16.1 min) | 91/113 (0.805) | 0/3/5/0/11/3 | 28 | 1/0 | 0 | 0 | 0 | 0 | 9/0 |
| E1 run 3 -- T062904Z | happy | $2.486589 | $2.482062 | $0.004527 | 946.7 s (15.8 min) | 101/113 (0.894) | 1/2/3/0/3/3 | 29 | 1/0 | 0 | 0 | 37 | 3 | 9(7 verdict)/0 |
| E2 run 1 -- T064929Z (WEDGED -- excluded from cost/latency stats) | realistic | $1.094919 | $1.085984 | $0.008935 | 8313.5 s (harness-side stall inflation) | 75/113 (0.664)* | 31/2/1/0/4/0 | 13 | 0/0 (spontaneous close, no GoAway) | 180 | 1 | 0 | 7 | 3/1 |
| E2 run 2 -- T090804Z | realistic | $3.460401 | $3.399272 | $0.061129 | 1202.8 s (20.0 min) | 72/113 (0.637) | 21/2/5/3/6/4 | 62 | 2/0 | 0 | 0 | 140 | 103 | 8(8 verdict)/1 |
| E2 run 3 -- T092808Z | realistic | $2.931827 | $2.924816 | $0.007011 | 2220.2 s (37.0 min) | 101/113 (0.894) | 0/3/4/0/5/0 | 34 | 1/0 | 26 | 0 | 0 | 5 | 9(7 verdict)/1 |

Notes on the table:
- "Evictions" = count of `eviction_drops` entries in the run's meta.json
  (context-window compression firings). All 8 runs' full eviction lists
  were counted directly from the artifacts.
- "reconnects (announced/spontaneous)" = `go_away_announced` / a
  reconnect that fired without an announced GoAway. All measured
  reconnects in E1/E2 were GoAway-announced (1 each, ~6-7.5s downtime)
  except the E2 wedge run, which had zero `reconnects` recorded despite
  the session dying -- see problem-case inventory, item "spontaneous-1011
  wedge."
- "stalls" = `stalled_turns` from `errors`. The E2 wedge run recorded 180
  stalled turns (the harness gap); T092808Z recorded 26 stalled turns
  (non-fatal, session continued) -- both are real observations, kept in
  the table, but only the wedge run's cost/wall-clock is excluded from
  aggregate stats.
- Fill accuracy asterisk on the wedge run: the underlying 0.664 accuracy
  number is real (75/113 matched) but reflects a session that terminated
  early via 1011 close plus 180 stalled turns -- it is a resilience
  data point, not a comparable happy/realistic-path accuracy figure.
- E0 pilot 1 (pre-fix) failure mode breakdown: 2 transcription + 1
  mismatch, all on the same 3-field cluster (family name / given name /
  middle name) -- this is the Nguyen-family-name transcription case
  (problem-case inventory item 1), distinct from the Denver/Hanoi organic
  catch in E1 run 1 (Section 4).

## 3. E1 (happy x3) aggregate stats

n = 3 runs (T055600Z, T061257Z, T062904Z), all clean (no wedge/stall).

| metric | mean | range (min-max) |
|---|---|---|
| all-in USD | $2.4429 | $2.4167 - $2.4866 |
| wall-clock | 975.9 s (16.26 min) | 946.7 - 1015.7 s (15.78 - 16.93 min) |
| fill accuracy | 0.858 | 0.805 - 0.894 |
| usd_per_correct_field (per-run mean) | $0.02523 | $0.02450 - $0.02656 |

(usd_per_correct_field computed per-run as all_in_usd / matched, then
averaged; taking mean-cost / mean-matched instead gives $0.02518 --
consistent to within rounding.)

## 4. E2 (realistic x3) seam results

n = 3 runs; T064929Z is the WEDGED run (1011 close + 180 stalls) --
included here only for the seam/planted-pair columns since those fired
before the wedge, excluded from cost aggregate framing above.

| run | secretary recall (fired/correct) | navigate-back (attempts / hit-rate) | seam latency p50 | skip recorded | validator planted P/R |
|---|---|---|---|---|---|
| T064929Z (wedged) | 1/1 fired-and-correct out of 2 recall events | 2 attempts / 0 hit (0%) | n/a (0 successful switches) | 1/1 | recall 0.5, precision 1.0 |
| T090804Z | 2/2 fired-and-correct out of 2 recall events | 2 attempts / 1 hit (50%) | 0.578 s | 1/1 | recall 0.5, precision 1.0 |
| T092808Z | 2/2 fired-and-correct out of 2 recall events | 2 attempts / 1 hit (50%) | 0.453 s | 1/1 | recall 0.5, precision 1.0 |

Planted-pair detail (identical across all 3 E2 runs):
- Planted pairs: `(p1_line6e_state, p1_line6f_zipcode)` [near ZIP/state
  pair] and `(p5_line1b_language, p6_language)` [far cross-section
  language pair].
- The near ZIP/state pair was **caught and corrected in every run**
  (steer outcome `corrected_no_switch`, e.g. "US ZIP code 98101 does not
  belong to Texas").
- The far p5/p6 language pair was **missed in every run**
  (`missed_groups: [["p5_line1b_language", "p6_language"]]`) -- validator
  windows are 20 fields wide and the two fields in this pair are farther
  apart than that in question order.
- Net: recall 0.5 (1 of 2 planted pairs caught), precision 1.0 (0 false
  positives) in all 3 E2 runs.

Organic (unplanted) catch, E1 run 1 (T055600Z): the validator flagged a
real transcription error that was not a planted pair. `switch_to_field`
on `p1_line10_citytownofbirth` shows `"current_value": "Denver"` while
the fill-accuracy detail for the same run records
`{"field_id": "p1_line10_citytownofbirth", "expected": "Hanoi", "written":
"Denver", "ok": false}` -- the model transcribed/filled "Denver" for a
field whose correct answer was "Hanoi." The validator's steer record for
this run shows `outcome: "overridden_unplanted"` on the
`(p1_line7c_cityortown, p1_line7d_state)` /
`(p1_line10_citytownofbirth, p1_line11_countryofbirth)` conflict pair,
confirming this was caught organically, not from a planted pair.

## 5. Problem-case inventory

- **Vietnamese-name transcription (Nguyen -> Smith pre-spell-out).** E0
  pilot 1 (T054615Z, pre-fix): `p1_line3a_familyname` expected "Nguyen,"
  written "Smith" (mismatch); `p1_line3b_givenname` expected "Linh,"
  written "Lynn" (transcription); `p1_line3c_middlename` expected "Thi,"
  written "T" (transcription). Fixed by pilot 2 (T055241Z, post-fix):
  same 3 fields all exact. No dedicated bead ID found in `bd list` for
  this specific finding as of this pass -- may be tracked only inside the
  stress-test epic `polyglot-pdf-00pt`.
- **Per-field `ask_secretary` spam mode.** T090804Z: 103 secretary calls
  in a single 113-question run (cache_hit_rate 0.641); E0 pilot 1 also
  showed 10/10 calls (one per field) before the per-field-name-lookup
  pattern was addressed. Bead filed: `polyglot-pdf-2af7` ("Voice model
  asks the secretary for each field's spoken name before asking it
  (per-field blocking waste)").
- **Checkbox-decline sometimes checks the box.** T061257Z:
  `p4_checkbox1a`, `p4_checkbox1b`, `p4_checkbox1c` all expected empty,
  all written `"true"` (3 spurious fills) -- a declined/no-answer
  checkbox path wrote a positive value. Bead filed: `polyglot-pdf-cx23`
  ("Voice decline on a checkbox sometimes CHECKS it ('true') -- wrong-
  answer class on legal forms").
- **Spontaneous-1011 wedge.** E2 run T064929Z: `close_1011: 1`, 180
  stalled turns, no `go_away_announced` (unlike the other reconnects in
  this data set, which were all GoAway-announced). This is a harness
  resilience finding -- the harness's gap in handling a spontaneous
  (non-announced) 1011 close has since been fixed in-harness; the
  production client's own reconnect path is a separate, already-shipped
  mechanism (see bd memory `1011-mitigation-landscape-already-mostly-
  done`).
- **Far-pair validator blindness.** All 3 E2 runs missed the
  `(p5_line1b_language, p6_language)` planted pair every time (recall
  0.5/run, consistent). Validator windows are 20 fields; the two fields
  in this pair are farther apart in question order than the near
  ZIP/state pair, which was caught in all 3 runs. A wider or
  cross-section-aware pass (W6 "pro pass") exists as a design but is not
  wired in any of these runs (`pro_pass.ran: false` in every summary.json
  read for this doc) -- to be measured in E3 per the epic
  `polyglot-pdf-09da`.
- **Secretary in-session cache hit far below probe rates.** Measured
  `cache_hit_rate`: 0.1 (T055241Z pilot 2), 0.25 (T055600Z), 0.0
  (T062904Z), 0.0 (T064929Z wedge), 0.641 (T090804Z), 0.0 (T092808Z) --
  i.e. 0-64% observed in-session, well below the 96-98% implicit-cache
  hit rates reported in prior standalone secretary-caching probes (see
  bd memory `secretary-text-model-caching-append-only`). Only T090804Z
  (the per-field-spam run, 103 calls) approached a high hit rate; the
  other 5 runs cluster at 0-25%.

## 6. Numbers not yet in

The following legs are not covered by the artifacts read for this draft
and are placeholders pending later measurement passes:

- **E3** (validator W6 pro-pass wired, far-pair recall re-measured)
- **E4** (not yet run/specified at draft time)
- **E6** (not yet run/specified at draft time)
- **Deployed-latency legs** -- all wall-clock and turn-latency numbers in
  this doc are from the **local** harness stack, which the maintainer has
  flagged as overstating real Cloud-Run-deployed latency (see Section 1
  and bd memory `harness-local-latency-overstates-deployed`). No
  deployed-latency measurement exists yet in this series.
