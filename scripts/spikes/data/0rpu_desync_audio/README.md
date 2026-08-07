# bd 0rpu -- spelled-read-back desync: evidence corpus

From the 2026-08-05/06 investigation (12 MB, 98 files):

- **41 curated output-audio clips** -- every generation the final scorer
  flagged, plus matched ALIGNED neighbours for contrast (from 274 captured).
- **`*__transcript.jsonl`** -- the LIVE MODEL's own record per run: what it
  said it was saying (`transcript` / `spoken_by_model`), every `tool_call` and
  `tool_response`, the `interrupted` events, `compression_config`, and the
  `audio_dump` records that tie WAVs to sequence ranges. Filtered from the raw
  dev logs (14.4 MB -> 3.2 MB) by dropping base64 audio frames and debug
  chatter; every analytically meaningful record is kept.
- **`*__stt_*.json`** -- the Cloud STT scoring passes: per generation, what the
  AUDIO actually said vs what the TEXT track claimed, with duration, confidence
  and the pairing window.
- **`*__driver.json`** -- what the harness asserted (fields filled/confirmed,
  playback backlog at each answer).
- **`*__tokens.jsonl`** -- per-turn token/cost curve; the prompt-token drops in
  here are how context-compression evictions were detected (they emit no event).

**The pairing:** for any generation, the `transcript.jsonl` gives the model's
intent, the matching `stt_*.json` row gives what the audio actually produced,
and the WAV lets you hear it. That triple is what makes the defect provable
rather than anecdotal.

> The retracted first-pass scorer output (`stt_report.json`, Gemini-as-STT) is
> deliberately NOT included -- it hallucinated sentences from sub-second clips
> and produced two findings that were withdrawn. See the findings doc.

**Content note:** synthetic form answers plus the maintainer's own name. No
third-party PII. Committed deliberately (maintainer decision 2026-08-07) so the
defect can be *heard* rather than re-derived.

## The defect these clips demonstrate

The native-audio model's SPEECH path returns to the **first name spelled in the
session**, regardless of which field is current, while its own text track and
every tool call stay correct. A **sticky first-spelling attractor**, not random
corruption.

Start with these two:

| clip | what to listen for |
|---|---|
| `reanchor_control__*_g9_*.wav` | `"J0hn John Joshua, is that correct?"` -- spells J-O-H-N, says "John", THEN says "Joshua". Text track said only "Joshua". STT confidence 0.864, so this is genuinely in the audio. |
| `night_runRUDE__*_g8_*.wav` | spells `J-O-H-N` while saying "Joshua" (the middle-name field). |

Then the NATO run (`spellback_nato__*`), gens 9 / 11 / 15: three *different*
names -- Joshua, Johnson, Jose -- and the audio emits the **identical**
corrupted utterance ("Joe Howa") each time. A recognizer mishearing three
different inputs produces three different errors; one wrong output across three
distinct inputs is the model.

For contrast, the ALIGNED clips in the same runs show the model spelling
correctly -- e.g. `M-A-R-I-A` -- so this is intermittent substitution, not a
model that simply cannot spell.

## manifest.json

One row per clip: source run, scorer verdict, what the AUDIO spelled vs what
the TEXT track spelled, duration, STT confidence, and both transcripts.

**Confidence is itself a signal.** Healthy generations score 0.93-0.99;
corrupted spelled read-backs score 0.34-0.65. A future scorer must NOT drop
low-confidence spelled rows from its denominator -- doing so deletes exactly
the failures it is measuring (this was one of five instrument defects found
during the investigation).

## Reading the runs

| prefix | arm |
|---|---|
| `night_runA` | compression OFF |
| `night_runB`, `night_runB2` | compression ON |
| `night_runRUDE` | deliberate mid-speech barge-ins |
| `night_runPOLITE` | drain-paced, barge-ins avoided |
| `reanchor_control` | post-PR-#550 baseline (9.7% desync) |
| `spellback_nato` | SI rule: NATO word anchors -- model IGNORED it |
| `spellback_comma` | SI rule: comma-paced letters -- model OBEYED, still wrong |
| `spellback_echo_once` | tool-response value echoed 1x instead of 3x |

**Every arm ran at `LIVE_TEMPERATURE=0.4`.** There is no 1.0 control in this
corpus, and production sends no temperature -- so these rates are "at 0.4", not
"at production settings".

## Regenerating

The capture path shipped in PR #556: set `LIVE_DEV_AUDIO_DUMP=true` (plus the
`backend/.env.DEV` marker) and run
`tests/e2e/voice-harness/driver_w7_desync.mjs`. Score with
`scripts/spikes/stt_readback_diff2.py`. Always run behind
`scripts/spikes/run_guard.py`. One run reproduces the defect for ~$1.

Full method, results, and two retracted findings:
`scripts/spikes/0rpu_desync_attribution_findings.md`.
