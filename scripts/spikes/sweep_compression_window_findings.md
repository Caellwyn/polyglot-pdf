# Compression window sweep -- findings (bd polyglot-pdf-45o, epic -l3a)

*Run 2026-06-04 against the real Live API (gemini-3.1-flash-live-preview) via the
production adapter, compression wired in per `docs/components/context-compression.md`.*

Harness: `scripts/spikes/sweep_compression_window.py` (cost from the adapter's
`token_usage.jsonl`; UX = response latency, send_activity_end -> first audio-out chunk).

## TL;DR -- the headline finding

**Compression did NOT bound `prompt_tokens` in any configuration measured.** Across
two live sweeps -- trigger=5000 (windows 2k/3k/4k + unbounded baseline) and trigger=2000
(windows 1k/1.5k) -- the per-turn `prompt_token_count` the API itself reports climbed
**monotonically** (10x-14x over 12 turns), with **no eviction** even on the turns where
the prompt clearly exceeded the configured `trigger_tokens`. Cumulative cost stayed
super-linear in every config. This contradicts the design doc's modeled
quadratic->linear plateau.

The config IS reaching the wire correctly (verified offline: the adapter's raw dict
serializes to `{triggerTokens, slidingWindow:{targetTokens}}`), so this is a **semantic**
result, not a wiring bug: for this model/config, server-side eviction did not take
effect on the billed `prompt_tokens` within a single ~12-turn audio session.

## Data

### Sweep 1 -- trigger 5000, turns 12, 1 run each

| config | prompt_growth | cum $ | lat median (s) | lat p90 (s) |
|---|--:|--:|--:|--:|
| unbounded (compression off) | 14.0x | 0.0712 | 0.84 | 1.56 |
| window 2000 / trigger 5000 | 11.8x | 0.0587 | 0.85 | 1.44 |
| window 3000 / trigger 5000 | 10.8x | 0.0535 | 1.15 | 1.78 |
| window 4000 / trigger 5000 | 12.6x | 0.0642 | 0.85 | 1.32 |

At 12 short turns the prompt peaks ~3.4k -- **below the 5k trigger**, so compression was
never even eligible to fire. (Confirms the design doc's warning that a high trigger is
inert for our short sessions; the cum-$ spread here is run-to-run noise, not a
compression effect.)

### Sweep 2 -- trigger 2000, turns 12, 1 run each (no baseline)

| config | prompt_growth | cum $ | lat median (s) | lat p90 (s) |
|---|--:|--:|--:|--:|
| window 1000 / trigger 2000 | 13.6x | 0.0698 | 0.94 | 1.61 |
| window 1500 / trigger 2000 | 12.6x | 0.0642 | 0.78 | 1.16 |

Here the prompt **crossed the 2000 trigger** by ~turn 8 (window-1500 run: turn 8 prompt
= 2,041; turn 12 = 3,395) -- yet prompt_tokens kept climbing past it with no drop back
toward the 1500 window. **This is the conclusive evidence that eviction did not take
effect.** If compression were honored, turns 8-12 should have billed against ~1500
retained tokens, not the full 3,395.

## UX (latency) -- the one clean positive

Response latency was **low and stable everywhere**: median ~0.8-1.1s, p90 ~1.2-1.8s,
max <1.8s. No configuration showed a latency penalty, including the (eligible)
low-trigger runs. So whatever compression does or doesn't do to cost, it does **not**
degrade response latency in these sessions. (Latency is the UX axis chosen for this
experiment; reply-coherence-after-eviction was explicitly out of scope.)

## What this does and doesn't establish

- **Establishes:** the experiment harness works end-to-end (cost + latency across
  window sizes, baseline included), and -- empirically -- enabling the documented
  compression config did not bound billed `prompt_tokens` on
  gemini-3.1-flash-live-preview within a single short audio session.
- **Does NOT establish the root cause.** Open hypotheses (NOT yet verified -- do not
  assume): (a) compression eviction may only manifest over **longer** sessions / more
  accumulated tokens than a 12-turn probe reaches; (b) `prompt_token_count` in
  usage_metadata may report processed-this-turn tokens that don't reflect eviction the
  way we modeled; (c) this specific native-audio preview model may not honor
  `contextWindowCompression` the same way the docs' general example assumes. A text
  probe to isolate (a)/(b) is NOT possible on this model -- it rejects TEXT modality
  with 1007 (native-audio emits AUDIO only).

## Recommendation

Keep `CONTEXT_COMPRESSION_ENABLED=False` (the shipped default) until the root cause is
understood -- the feature is wired and reversible behind one env var, but it is **not
yet validated as delivering the cost win**. Root-cause investigation is filed as a
follow-up bead (does not block the wiring/harness this bead delivered). The design
doc's modeled cost table remains **modeled, not measured-confirmed**; this run is the
measured-reality check the doc called for, and it came back negative on the plateau.
