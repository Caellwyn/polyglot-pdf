# Three-arm token-cost matrix: findings (bd polyglot-pdf-wyhh)

*Date: 2026-06-12. Epic: polyglot-pdf-hcsl (sprint 4). Instrument: bd
polyglot-pdf-4loz (`measure_form_session_costs.py`). Data:
`scripts/spikes/data/costs_<model>_<arm>_<path>_<stamp>.csv` (the 11-column
per-question CSVs) + `.meta.json` sidecars (per-turn latency, tool calls,
prompt curves, errors). 12/12 cells ran; total live spend ~USD 10.6.*

## The matrix (20 questions per run; happy = 2 turns/q, unhappy = 4 turns/q)

| model | arm | path | total tokens | total cost | text-in share | evictions | confirmed | stalled turns | median turn latency |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2.5 | section-reset | happy | 213,867 | $0.188 | 95.0% | (3 restart drops) | 16/20 | 0 | 2.17s |
| 2.5 | section-reset | unhappy | 444,425 | $0.324 | 96.4% | (2 restart drops) | 15/20 | 11 (*) | 2.61s |
| 2.5 | sliding-window | happy | 534,428 | $0.330 | 98.0% | 0 | 15/20 | 0 | 1.75s |
| 2.5 | sliding-window | unhappy | 1,342,518 | $0.797 | 97.9% | 2 | 19/20 | 0 | 1.73s |
| 2.5 | unbounded | happy | 535,613 | $0.338 | 97.9% | 0 | 13/20 | 0 | 1.81s |
| 2.5 | unbounded | unhappy | 1,317,634 | $0.781 | 98.0% | 1 | 18/20 | 0 | 1.61s |
| 3.1 | section-reset | happy | 341,266 | $0.627 | 58.1% | (4 restart drops) | 19/20 | 0 | 1.84s |
| 3.1 | section-reset | unhappy | 840,219 | $1.729 | 46.9% | (22 restart drops) | 20/20 | 0 | 1.75s |
| 3.1 | sliding-window | happy | 828,400 | $1.023 | 81.2% | 4 | 20/20 | 0 | 1.88s |
| 3.1 | sliding-window | unhappy (+) | 927,189 | $1.184 | 79.4% | 16 | 12/20 | 29 (+) | 1.81s |
| 3.1 | unbounded | happy | 1,047,190 | $1.624 | 67.0% | 4 | 18/20 | 0 | 1.81s |
| 3.1 | unbounded | unhappy (+) | 1,078,528 | $1.686 | 66.5% | 13 | 10/20 | 34 (+) | 1.72s |

(*) one mid-section `1006 abnormal closure` (the bd-daa transient class) killed
that section's session; the driver does not auto-reconnect mid-section the way
the production client (vmxx) does, so turns stalled until the next section
boundary restarted the session. Costs for that patch are under-counted.

(+) TRUNCATED BY SESSION-DURATION GoAway -- see the headline finding below.
Questions ~13-20 in those two runs ran against a dead connection; their rows
record ~0 tokens. Real full-run costs for 3.1 unbounded/sliding-window unhappy
are HIGHER than shown.

Arm scoping: `section-reset` = the production flow (per-section sub-schema,
`switch_to_section` restart at each boundary; restart + re-greeting tokens are
attributed to the first question of the new section). `unbounded` /
`sliding-window` = one whole-form session (the full 174-field schema in the
system instruction -- what "no sections" honestly costs with today's SI
machinery). Sliding-window config: trigger=12,000 / window=9,000, sized above
the whole-form SI base. "(n restart drops)" in the section-reset rows: the
eviction detector keys on prompt-token drops, and a session restart resets the
curve -- those are NOT compression evictions.

## Headline findings

1. **Section resets beat the sliding window on cost -- decisively -- under the
   current SI architecture.** 2.5 happy: $0.188 vs $0.330 (sliding) vs $0.338
   (unbounded); 2.5 unhappy: $0.324 vs $0.797/$0.781. The reason is structural:
   **the dominant cost is the per-turn re-billed system instruction, and
   compression cannot evict it.** The whole-form SI bills ~8.1-8.2k tokens at
   turn 1 (97-98% of 2.5's total spend was text-in); the sliding window only
   evicts conversation history above that floor, and with window=9,000 over a
   ~8.2k base the evictable mass is a rounding error (0-2 evictions fired on
   2.5). Section resets attack the floor itself (the per-section SI greeting
   billed ~2.3k on 3.1). Compression only becomes interesting paired with a
   much smaller instruction (e.g. the JIT path) -- that is an architecture
   question for the go/no-go brief, not a tuning knob.

2. **A single-session whole-form flow CANNOT ship on compression alone: the
   session-duration GoAway still arrives.** Both 3.1 single-session unhappy
   runs died at ~question 12-13 (~50 turns, ~13-15 min) with
   `1008 Connection aborted because the client failed to close the connection
   after receiving a GoAway signal once the session durat[ion limit ...]` --
   **with compression ON and demonstrably evicting (16 drops)**. Compression
   lifts the context-size cap; the session-duration limit is separate and is
   handled by the GoAway -> reconnect -> session-resumption path (GoAway
   forwarding shipped, bd c5t; the reconnect POLICY is open, bd l3a.2; resumption
   adoption decided for unintentional disconnects, bd wnt/l3a.3). The headless
   driver ignores GoAway by design (it has no reconnect), which faithfully
   demonstrates what happens to any client that does not act on it. The
   2.5 runs finished under the limit (faster turns); this is a wall-clock
   ceiling every long-session design must handle, not a 3.1 quirk.

3. **No latency penalty at eviction events.** Median turn latency
   before vs after the first eviction: 3.1 happy 1.86s -> 1.89s; 3.1 unhappy
   1.88s -> 1.81s; 2.5 unhappy 2.19s -> 1.59s (faster after -- smaller
   prompts). The compression event is invisible in turn latency at these sizes.

4. **Tool-call compliance held up across arms; the variance is per-question,
   not per-arm.** Most questions show the expected pattern (update + confirm on
   happy; 2x update + confirm on unhappy). Lapses (a missed confirm_field, a
   verbal-only confirmation) appear in every arm at similar rates, EXCEPT the
   truncated 3.1 cells whose post-GoAway questions could not comply at all.
   Confirmed-field counts: 13-20/20 on live sessions. Per-question tool logs
   are in each meta sidecar (`per_question_tools`).

5. **3.1 costs 3-5x more than 2.5 for the same work** ($0.63-1.73 vs
   $0.19-0.80 per run): higher text-out rate (4.50 vs 2.00/1M) on much more
   output (thinking tokens bill as output on 3.1 -- its text-in share drops to
   47-81% because output dominates). With tool-call reliability now equal
   (bd wpw.4) and 2.5's lower latency, 2.5 remains the production tier on
   every axis measured here.

## Method notes (for the elbow analysis, bd 6x1y)

- Per-question numbers are deltas over the adapter's cumulative per-modality
  counters; section-restart greetings are charged to the question that needed
  the restart (that IS the cost of advancing). The whole-session greeting is
  excluded from question 1 (recorded separately as `greeting_tokens` in meta).
- The 11-column CSVs are the contract deliverable; everything else (latency,
  tools, prompt curves, eviction drops, errors) lives in the `.meta.json`
  sidecars next to each CSV.
- Prompt curves (`prompt_curve` in meta) give the turn-memory-vs-context-length
  distribution the elbow analysis needs; the unbounded arms are the raw growth
  curves, per path and model.
- Deploy fidelity per docs/standards/testing.md: real FormFillingService +
  CallbackHandler + RequestCoordinator + production SYSTEM_INSTRUCTION and
  TOOL_DECLARATIONS; the frontend simulated (state ownership, hint format,
  synchronous confirm round-trip). Labeled deviations: explicit activity
  brackets with server VAD neutralized; no GoAway reconnect (which is itself a
  finding, see #2); gTTS audio (cached under `fixtures/audio_cache/`).

## Reproduce

```
backend/.venv/Scripts/python.exe scripts/spikes/measure_form_session_costs.py \
    --model 2.5 --arm section-reset --path happy            # one cell
```

All 12 cells = {--model 2.5|3.1} x {--arm unbounded|section-reset|sliding-window
[--trigger 12000 --window 9000]} x {--path happy|unhappy}.
