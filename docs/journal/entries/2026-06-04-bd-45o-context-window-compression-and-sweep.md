---
date: 2026-06-04
bead: polyglot-pdf-45o
title: "Implement ContextWindowCompressionConfig in the Gemini Live adapter"
tags: [performance, testing]
---

## Trigger

Phase 3 of epic `polyglot-pdf-l3a` (Live API context-window compression). The spike
(`tak`) and design (`nv0`) were done; the design doc
([context-compression.md](../../components/context-compression.md)) carried a *modeled*
cost table across window sizes but no *measured* numbers. The maintainer asked to "set
up some experiments to track costs and UX empirically across different context window
sizes" -- which is exactly `45o`'s validation step, generalized from a single re-run
into a parameter sweep. That requires the compression config to exist first (it did
not), so this bead wires it in and then sweeps it.

## What shipped

1. **Compression config, env-swappable** (`backend/config.py`):
   `CONTEXT_COMPRESSION_ENABLED` (default `False`), `CONTEXT_COMPRESSION_TRIGGER_TOKENS`
   (5000), `CONTEXT_COMPRESSION_WINDOW_TOKENS` (3000), plus a validator clamp ensuring
   window < trigger (the API requires it) so a misconfig can't send a rejected config.
2. **Adapter wiring** (`backend/adapters/live_ai_gemini.py`): emits the
   `context_window_compression` dict in the `connect()` config alongside the other
   optional keys, gated on the flag. The dict syntax was verified against the installed
   `google-genai` -- both a typed `LiveConnectConfig` and a raw dict serialize to the
   correct `triggerTokens`/`slidingWindow`/`targetTokens` wire form.
3. **Unit tests**: present-when-enabled, absent-when-disabled, window-clamp.
4. **Sweep experiment harness** (`scripts/spikes/sweep_compression_window.py`): drives
   the same scripted audio session per window size + an unbounded baseline, capturing
   per-turn tokens, cumulative cost (from the adapter's `token_usage.jsonl`), and
   **response latency** (send_activity_end -> first audio-out chunk -- the UX axis the
   maintainer chose). Emits a comparison table + CSV. The per-window override is done by
   constructing `Settings(**kwargs)` and patching `get_settings`, because `Settings`
   binds env defaults at import time (mutating `os.environ` mid-process is a no-op).

**Headline finding (negative): compression did NOT bound `prompt_tokens`.** A small
live sweep (the maintainer's chosen scope) across triggers 5000 and 2000 and windows
1k-4k showed the API's own `prompt_token_count` compounding 10x-14x over 12 audio turns
with no eviction -- even on turns where the prompt clearly exceeded `trigger_tokens`
(window-1500/trigger-2000: turn 8 prompt = 2,041, turn 12 = 3,395, never dropped). The
config reaches the wire correctly, so this is a *semantic* result on
`gemini-3.1-flash-live-preview`, not a wiring bug. The one clean positive: response
latency was low and stable everywhere (median ~0.8-1.1s, p90 ~1.2-1.8s) -- no latency
cost from enabling compression. Full data in
`scripts/spikes/sweep_compression_window_findings.md`.

**Deferred / filed:** root-cause investigation filed as **`polyglot-pdf-l3a.1`**
(open, P1, under the epic). Because compression is unvalidated as a cost win, the
shipped default stays `CONTEXT_COMPRESSION_ENABLED=False` -- the code is wired, tested,
and reversible behind that one env var. A text-modality probe to isolate the cause was
attempted and removed: native-audio models reject TEXT (1007), so the probe can't run.

## Lessons

- **Validate the vendor claim, don't trust the model.** The design doc's
  quadratic->linear plateau was directional math; the first real measurement came back
  negative. The harness paid for itself immediately by catching that the documented
  compression config does not (yet) deliver the win on our model -- before anyone
  flipped the flag in prod expecting savings.
- **`Settings` binds env at import.** A fresh `Settings()` does not re-read `os.environ`;
  per-run config overrides in-process must pass explicit kwargs (or patch
  `get_settings`), not mutate env. This is why the sweep injects settings rather than
  setting env between runs.
- Native-audio Live models emit AUDIO only (TEXT=1007) -- reinforced the existing
  scar; it blocks the cheap text-based diagnostic path for compression semantics.

## Doc freshness

- **Bumped:** [docs/components/context-compression.md](../../components/context-compression.md)
  -- replaced the "Validation (for 45o)" section with a "Validation status -- measured
  NEGATIVE" section recording the sweep result, pointing at the findings doc and
  `l3a.1`, and flagging the modeled cost table as not-yet-confirmed.
- **Reviewed and left as-is:** the doc-freshness checker flagged `voice-ai.md`,
  `ai-models.md`, `hipaa-pii-policy.md`, `logging-and-cost.md`, `risk-rating.md`,
  `voice-and-vad.md`, `config-deployment.md`, `confirmation-and-audit.md`,
  `technical_guide.md` as stale -- all by *mtime* (they track `config.py` /
  `live_ai_gemini.py`, which this branch touched). This change is a narrow,
  default-off gated config addition that does not alter those docs' current-state
  prose; they were already stale before this branch (timestamps 2026-06-01/02). Left
  unbumped per the closeout rule (a stale doc tracking files the branch didn't
  substantively change stays as-is, noted here).

## Files touched

- `backend/config.py` -- added 3 compression settings + window<trigger clamp.
- `backend/adapters/live_ai_gemini.py` -- emit `context_window_compression` in connect config (flag-gated).
- `backend/tests/unit/test_live_ai_gemini.py` -- 3 compression-config tests.
- `scripts/spikes/sweep_compression_window.py` -- new window-size sweep harness (cost + latency).
- `scripts/spikes/sweep_compression_window_findings.md` -- new measured findings.
- `docs/components/context-compression.md` -- validation-status update (measured negative).
