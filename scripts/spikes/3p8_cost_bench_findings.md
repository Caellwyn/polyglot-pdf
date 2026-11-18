# gemini-3.8-live cost and latency benchmark (bd polyglot-pdf-e72on)

**Date:** 2026-11-18 (UTC).

**Models:**
- `gemini-3.8-live` and `gemini-live-2.5-flash-native-audio`, both on Vertex us-central1.
- The model id was checked in every run's `.meta.json`.
- Helpers: `gemini-2.5-pro` pro pass and the lite validator, as in production.

**Instrument:** `scripts/spikes/measure_form_session_costs.py`, in-process, with:
- the strict W-7 answer key (bd r3ham.14), so W-7 fill accuracy is exact or any-of on all 22 fields;
- the turn-audio audit (bd r3ham.1);
- the adapter transcript fix (bd r3ham.6).

**Config (production fidelity):**
- `--arm dti --continuous --compression --derive-compression --text-ai --pro-pass --audit-transcripts`.
- `LIVE_TEMPERATURE=0.4`, `SPELLBACK_TOOL_ENABLED=true`, push-to-talk activity brackets.
- Input and output transcription on, session resumption off. These are the production defaults.

**Runs:** 12, serial. Each group is n=3 on the same script.

**Spend:** $16.40 (sum of `all_in_usd`).

**Raw data:** `scripts/spikes/data/r3ham/bench/`:
- per run: `.summary.json`, `.meta.json`, a per-question `.csv` and a per-turn `.turns.csv`;
- the input-transcription probe: `input_transcription_probe_3p8.json`.

## Headline

| Group (n=3) | $ / form, mean (range) | Fields correct, strict | $ / correct field | First-audio p50 / p90 (local, pooled) | Wall clock | GoAway |
|---|---|---|---|---|---|---|
| W-7 happy, **3.8** | **$0.905** ($0.867-0.937) | 21, 21, 21 of 22 | $0.043 | 1.16 s / 1.34 s (n=108) | 357-447 s | 0 of 3 |
| W-7 happy, **2.5** | **$0.697** ($0.672-0.736) | 19, 22, 21 of 22 | $0.034 | 1.31 s / 1.44 s (n=93) | 221-236 s | 0 of 3 |
| W-7 unhappy (every answer corrected once), 3.8 | $1.709 ($1.499-1.829) | 20, 19, 19 of 22 | $0.088 | 1.14 s / 1.38 s (n=176) | 469-894 s | 2 of 3 |
| I-90 v2 happy, 3.8 | $2.154 ($1.292-2.711), **every run aborted early** | lenient 27, 13, 11 of 57 | not meaningful | 1.13 s / 1.30 s (n=188) | 852-1469 s | 3 of 3 |

**Cost: on the like-for-like W-7, 3.8 costs about 30% more per form than 2.5** ($0.905 vs $0.697), and about 27% more per correct field.
- This reverses the n=1 smoke result of 2026-11-17, where 3.8 looked about 4% cheaper ($0.76 vs $0.79). At n=3 both groups are tight (ranges of $0.07 and $0.06), so the gap is real.
- The prompt is about the same size on both models (612k vs 636k text-in tokens per form). The gap comes from three places:
  - 3.8's text-in rate is 1.5x 2.5's ($0.75 vs $0.50 per 1M);
  - 3.8 speaks about twice as much audio (4.9k vs 2.6k audio-out tokens per form);
  - 3.8 bills thinking.
- 3.8 also runs longer: 357-447 s per W-7 against 221-236 s. That is mostly the extra speech; the harness waits for the model to finish speaking each turn.

**Latency did not regress.** First-audio latency is measured from push-to-talk release to the first audio byte, on the LOCAL harness. Pooled over n=3:
- 3.8 p50 1.16 s against 2.5's 1.31 s;
- the n=1 smoke had the opposite order (1.19 s vs 0.81 s);
- across runs and groups the medians sit between 1.0 s and 1.36 s, so neither model is reliably faster.

These are local numbers and overstate the deployed product, whose backend is co-located with the model. Deployed latency is in PR #908's telemetry and is not re-measured here.

**Fill accuracy on W-7 is equivalent; 3.8 is more consistent.**
- 3.8's only miss in all three happy runs is the same one: `name_1a_first` stored as `Anna` for "My first name is Ana, spelled A - N - A."
- 2.5 stored `Anna` in 1 of 3 runs, and made three digit errors that 3.8 did not:
  - passport number `104722285` for 10472285;
  - expiry `08/30/2021` for 08/30/2029;
  - birth date `03/14/1980` for 03/14/1990.
- The fixture now renders as letters (bd r3ham.14 re-voiced it, and STT reads it as letters). So 6 of 6 3.8 runs normalizing a spelled "A-N-A" to "Anna" is a model stored-value error. It is the same class as bd r3ham.15 (JOSE -> JOSHUA, JOHN -> JOHNSN). The `name_spellback` TTS clip spells the stored value, so a real user would hear "A-N-N-A" and could correct it. The scripted user always says yes.

## Cost split by modality (thinking as its own line)

Mean $ per form. Thinking tokens are billed at the text-output rate. The adapter's `text_output_tokens` includes them, so the "text-out" line below excludes thinking.

| Line | W-7 happy 3.8 | W-7 happy 2.5 | W-7 unhappy 3.8 | I-90 v2 3.8 (aborted) |
|---|---|---|---|---|
| Text in | $0.459 (50.0%) | $0.318 (45.2%) | $0.785 (44.3%) | $0.731 (33.8%) |
| Audio in | $0.365 (39.7%) | $0.352 (49.9%) | $0.821 (46.4%) | $1.215 (56.2%) |
| Audio out | $0.059 (6.4%) | $0.031 (4.4%) | $0.101 (5.7%) | $0.154 (7.1%) |
| **Thinking** | **$0.026 (2.8%)** | $0 | $0.046 (2.6%) | $0.045 (2.1%) |
| Text out, excluding thinking | $0.011 (1.1%) | $0.003 (0.5%) | $0.018 (1.0%) | $0.015 (0.7%) |
| Thinking tokens per form | 5.7k | 0 | 10.2k | 10.0k |

Source: the per-turn `token_usage` lines of each run log. Their sum matches the harness's `voice_usd` to within about 3%. Helpers (pro pass and validator) add under $0.003 per form and are excluded from the split.

- **On 3.8, text-in is the largest line on W-7 happy (50%), with audio-in close behind (40%).** On 2.5 the two lines are even (45% / 50%).
  - The order flips with session shape. In the longer sessions (unhappy W-7, I-90) audio-in leads on 3.8 too, because corrected answers and repeated questions add user audio.
  - So "text-in and audio-in are the two cost lines, together 85-95%" holds on both models. Which of the two is larger depends on the form and the path.
- **Thinking is small: 2-3% of the form.** It is about 260 thinking tokens per W-7 question, and they are output-rate tokens that don't stay in the context.
- **Compression evicts more on 3.8:** 12-16 evictions per W-7, against 6 on 2.5. The longer 3.8 speech fills the window faster; the compression floor and window themselves are unchanged.

## Input transcription cost (asked by the epic orchestrator)

**Question:** does `input_audio_transcription` (always on in production) add billed tokens on 3.8?

**Method:** `scripts/spikes/probe_input_transcription_cost.py`. It ran 6 push-to-talk turns with input transcription on and 6 with it off, on the production tool set, and summed `usage_metadata` per modality.

| Per turn, mean | On | Off | Delta |
|---|---|---|---|
| Text in | 1333.5 | 1317.8 | **+15.7** |
| Text out | 35.8 | 20.2 | **+15.7** |
| Audio in | 305.3 | 306.0 | -0.7 |
| Audio out | 137.5 | 135.2 | +2.3 |
| Thinking | 57.3 | 52.7 | +4.7 |
| Input-transcript chars | 32.3 | 0 | +32.3 |

**Verdict: yes, but it is negligible.**
- The transcript of the user's speech is billed as text-out when it is produced, about 1 token per 2 characters. It is then carried in the context as text-in.
- Audio is unchanged.
- At 3.8 rates this is about $0.00008 per turn: about $0.002-0.004 per W-7 form, or 0.3-0.4% of the form cost.
- Every benchmark number above already includes it, because production has it on.
- n=6 per arm. The text-out delta is stable across turns, because it tracks the length of the user's utterance.

## GoAway, reconnect, and the I-90 aborts

- **Every 3.8 session that ran past about 10 minutes received a GoAway** (`time_left=30s`). That was 5 of 5 such sessions: 3 I-90 and 2 unhappy W-7.
  - The harness reconnected without resumption, which is the production default.
  - This matches the July 2.5 series, which reported "the ~10-minute session cap is a non-event (silent reconnect)". The GoAway timing is unchanged vs 2.5.
- **The reconnect itself was clean in all 3 reconnects that happened before the session had desynced.** The other 3 reconnects (I-90 runs 2 and 3) came after the q17 desync below:
  - On W-7 unhappy, both reconnected runs finished with 20/22 and 19/22, the same as the run that did not reconnect (19/22).
  - In I-90 run 1, the session reconnected before q32 and filled q32-q36 normally afterwards.
  - This is new evidence for bd r3ham.11: post-reconnect degradation did NOT reproduce independently of a desync in these runs.
- **All three I-90 runs were aborted by the harness's derailment guard** (6 consecutive questions with no tool call):
  - **Runs 2 and 3** desynced at q17 (`phys_street`, script "same, 2140 Elmwood Drive"). The model wrote `''` and then ran behind or went silent. This is bd r3ham.10, now 3 of 4 I-90 runs counting the smoke run. In run 3, the silence began at q18, before that session's GoAway arrived.
  - **Run 1** got past q17 correctly. It went tool-silent at q37, the first Part 3 question (`p3_location_applied`), right after a q35 (`status`) turn where it called `get_form_status`, `ask_secretary` and `switch_to_field` instead of writing. n=1; filed as bd r3ham.16.
- **The I-90 lenient score is not a fill-accuracy number.** The I-90 v2 key is still empty, so the scorer counts any non-empty value as correct. It also counts correctly-blank fields (`mail_in_care_of`, `mail_unit_type`, `mail_province`, ...) as misses. Read the I-90 row as "how far the run got before derailing": q42, q36 and q23 of 57. The 2.5 reference on 2026-08-28 (bd 2nikx) scored 48/57 on the same scorer, so it reached at least q48.

**Practical reading:** on 3.8, a full I-90 does not currently complete on the scripted happy path. The cause is the q17 "same as mailing" write (r3ham.10) and a Part 3 stall, not the session cap. That makes r3ham.10 the blocker for any 3.8 I-90 figure in the pitch material.

## Caveats

- **Local harness.** Latency is local; the cost and token numbers are model-side and do not depend on where the backend runs.
- **Scripted user.** The user is gTTS fixtures and always says yes on the happy path, so a wrong stored value is never corrected.
- **2.5 retires on Vertex on 2026-12-13.** The 2.5 group is the prior record, not an alternative.
- **The W-7 unhappy path was run on 3.8 only,** as the epic plan asked; there is no 2.5 unhappy comparison in this batch.
