# tak spike findings — Live-session token+cost curve (bd polyglot-pdf-tak)

Baseline measurement for epic `polyglot-pdf-l3a` (context-window compression).
Produced by `scripts/spikes/measure_live_token_curve.py` (real-audio probe: gTTS
spoken prompts → 16k PCM16, bracketed by activity_start/end, driven through the
production adapter so its existing token logging records the curve).

**Run:** `gemini-3.1-flash-live-preview`, 8 audio turns, 1 session, 2026-05-31.
(2.5 native model excluded — it 1011s on the audio path; tracked in `polyglot-pdf-daa`.)

## The curve (per turn)

| Turn | Prompt tok | (audio) | Resp tok | Turn tok | Turn cost | Cum tok | Cum cost |
|-----:|-----------:|--------:|---------:|---------:|----------:|--------:|---------:|
| 1 | 271 | 78 | 68 | 339 | $0.001169 | 339 | $0.001169 |
| 2 | 437 | 201 | 33 | 470 | $0.001132 | 809 | $0.002300 |
| 3 | 551 | 286 | 66 | 617 | $0.001791 | 1,426 | $0.004091 |
| 4 | 753 | 441 | 98 | 851 | $0.002659 | 2,277 | $0.006750 |
| 5 | 973 | 608 | 114 | 1,087 | $0.003372 | 3,364 | $0.010122 |
| 6 | 1,274 | 845 | 95 | 1,369 | $0.003879 | 4,733 | $0.014001 |
| 7 | 1,494 | 1,012 | 148 | 1,642 | $0.005035 | 6,375 | $0.019036 |
| 8 | 1,799 | 1,243 | 132 | 1,931 | $0.005564 | 8,306 | $0.024600 |

## Findings

1. **Context compounds: prompt tokens grew 271 → 1,799 (6.6× over 8 turns).** Every
   turn re-bills the entire accumulated context. This is the cost lever `l3a` targets.
2. **Per-turn cost rose ~4.8×** (turn 8 = $0.00556 vs turn 1 = $0.00117) — the *same*
   ~1 turn of speech costs progressively more, purely from re-billed history.
3. **Cumulative cost is super-linear** ($0.0246 over 8 short turns, accelerating). A
   real session (longer turns, more of them, ~25 tok/sec audio accrual) gets much
   worse — the prompt's AUDIO portion dominates the growth (78 → 1,243 audio tokens
   re-billed per turn), and audio input bills 6× text.
4. **Bounded/compressed context directly caps this.** If the context were held to a
   sliding window of, say, ~the last few turns instead of the full history, per-turn
   prompt tokens would plateau instead of climbing 6.6× — flattening the cumulative
   curve from super-linear toward linear. That is the prize `nv0` should design for.

## Caveats

- Scripted cadence (fixed prompts, paced chunks), so ABSOLUTE per-second accrual is
  approximate; the COMPOUNDING shape (the point) is measured directly and is robust.
- Single session/run — directional baseline, not a statistical study. Re-run with
  more turns/sessions if a tighter number is needed for the design.
- Required a local workaround for `polyglot-pdf-p1t` (default VAD config 1007s on
  connect) to run at all.

## Reproduce

```
PYTHONPATH=. backend/.venv/Scripts/python.exe scripts/spikes/measure_live_token_curve.py \
    --turns 8 --runs 1 --csv scripts/spikes/tak_token_curve.csv
```
(Needs `GEMINI_API_KEY` + network for gTTS. Reads/writes `backend/logs/token_usage.jsonl`.)
