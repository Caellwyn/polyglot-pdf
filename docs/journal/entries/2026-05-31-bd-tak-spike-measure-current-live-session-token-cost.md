---
date: 2026-05-31
bead: polyglot-pdf-tak
title: "Spike: Live audio token+cost curve (compounding context) + session-end summary"
tags: [performance, testing]
---

## Trigger

Phase 1 of epic `polyglot-pdf-l3a` (Live API context-window compression). Before
designing compression (`nv0`), quantify the prize: how does the Gemini Live context
window — and thus per-turn cost — grow over a multi-turn session? The Live API bills
by a compounding context (every turn re-bills all accumulated tokens), so this spike
measures the actual curve to anchor the design.

## What shipped

A real-audio measurement harness + the baseline curve, plus one production logging
improvement.

**Harness** (`scripts/spikes/measure_live_token_curve.py`, throwaway): synthesizes
spoken prompts with gTTS → 16k mono PCM16 (decoded via `soundfile`, no ffmpeg/librosa
needed), streams them through the production adapter bracketed by
`activity_start`/`activity_end`, and reads the adapter's existing per-turn token
logging (`backend/logs/token_usage.jsonl`) back into a curve. Reuses existing
instrumentation rather than adding new.

**Why audio, not text:** the first cut used text turns, but the maintainer flagged
that audio is billed ~6× text for input — a text probe measures the wrong cost basis.
Rewrote to drive real synthesized audio. Confirmed on the audio basis (audio_input
tokens > 0).

**The baseline curve** (`gemini-3.1-flash-live-preview`, 8 audio turns):
prompt tokens grew **271 → 1,799 (6.6×)**; per-turn cost rose ~4.8×; cumulative cost
super-linear ($0.0246 over 8 short turns, accelerating). Full table in
`scripts/spikes/tak_token_curve_findings.md`. This directly confirms the compounding
re-billing model and shows bounded/compressed context is the lever `nv0` should design
for.

**Production change (part B):** `backend/adapters/live_ai_gemini.py` `finalize()` now
emits a `session_cost_summary` log line (counts/costs/ids only, no PII; guarded).
Previously the cumulative session cost was computed but **lost on teardown** — only
per-turn lines were logged. Small, useful beyond the spike (feeds the dashboard /
future BigQuery phase).

**Review (fresh-eyes + Copilot round 1, parallel — strongly overlapping):**
- **Adopted (fixed in PR):**
  1. `finalize()` summary could double-emit on concurrent/repeat finalize (race:
     drop + close), double-counting session cost downstream. Added a once-per-session
     guard (`_cost_summary_emitted`, reset at session start) + only emit when
     `total_tokens > 0`. *[fresh-eyes F1 + Copilot]*
  2. `gemini_session_id`/`model` in the summary were redundant/misnamed — the logger
     is already bound with `instance_id` + `model`; dropped them. *[Copilot]*
  3. Harness `clear_log()` destroyed `token_usage.jsonl` (real local logs / dashboard
     history). Removed it — we filter by synthetic `form_session_id`, so clearing was
     never needed. *[fresh-eyes F4 + Copilot]*
  4. Misleading "gTTS synthesis failed" message (the decode failure can be
     soundfile/libsndfile MP3, not gTTS). Reworded. *[fresh-eyes F5]*
- **Noted (not changed):** turn pacing waits on token-billing +1s, not response
  completion — could undercount in principle, but this run's curve was cleanly
  monotonic so it didn't bite; recorded as a caveat in the findings artifact.
  *[fresh-eyes F3]*
- **Rejected:** monkeypatch-vs-frozen-Settings (hypothetical future; throwaway
  spike), logger-path divergence (low-confidence; both anchored to `__file__`).
  *[fresh-eyes F2, F6]*
- **Copilot:** round 1 = 2 inline comments (both adopted; overlapped fresh-eyes).

**Discovered during the spike, filed separately (NOT fixed here):**
- **`polyglot-pdf-p1t`** (P2): the default VAD config sends
  `automatic_activity_detection.disabled=true` AND the sensitivity/padding fields
  together → Live API **1007** on connect. On dev AND main; prod unaffected only
  because the demo hasn't been redeployed since these changes. The spike carries a
  harness-local workaround (zeroes the VAD_* fields) — no prod change.
- **`polyglot-pdf-daa`** (REOPENED): the 2.5 native model
  (`gemini-2.5-flash-native-audio-preview-12-2025`) hit **1011** on the first real
  audio turn, while 3.1 was stable. The earlier "not affected" close was based on a
  *text* probe that never exercised the audio path — so it missed exactly the
  forum-reported failure. 2.5 is excluded from the harness until `daa` resolves.

## Lessons

- **Measure the real cost basis.** Audio-to-audio sessions bill audio at ~6× text;
  a text probe would have produced a confident but wrong cost curve. When measuring
  cost/perf, drive the modality the system actually uses.
- **A real-path probe finds what a proxy can't.** Driving real audio surfaced two
  defects (p1t 1007, 2.5 1011) that the text probe — and the prior `daa` text
  investigation — completely missed. Exercise the actual path, not a stand-in.
- **`_session_ready`, not `is_session_active()`,** is the true "session connected"
  signal for the adapter — driving turns before it caused "ACTIVITY_START called but
  session is None" and dropped turn 1.

## Doc freshness

- `docs/standards/logging-and-cost.md` tracks the adapter's token logging. The
  session-end cost summary added in `finalize()` is a small new emission in that
  area; reviewed the doc — its Phase-1 "per-event + per-session token+cost to JSONL"
  scope already covers it (the summary realizes the per-session half on teardown).
  No prose change required; noted here. Left other tier-2 docs untouched.
- `check_doc_freshness.py`: clean for tracked tier-1/tier-2 docs.

## Files touched

- `scripts/spikes/measure_live_token_curve.py` (new) — real-audio token+cost probe
- `scripts/spikes/tak_token_curve_findings.md` (new) — the curve + findings artifact
- `scripts/spikes/.gitignore` (new) — ignore the regenerable summary CSV
- `backend/adapters/live_ai_gemini.py` — session-end cost summary in finalize() (part B)
