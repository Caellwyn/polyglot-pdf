# Sprint 25 -- simulated user for the Live-voice measurement harness

Epic: `polyglot-pdf-ya4vi`. Children: E.1 `polyglot-pdf-ctzze`, E.2 `polyglot-pdf-wqnxr`, E.3 `polyglot-pdf-tmu0f`, E.4 `polyglot-pdf-15j9v`.
Approved by the maintainer 2026-11-18.

## Why

The gemini-3.8-live benchmark (epic `polyglot-pdf-r3ham`) drove the model with
fixed scripted answers. Those numbers partly measure how brittle the script is,
not only the model:

- when a name was not spelled, 3.8 kept asking for the spelling and W-7 stalled
  at 2 of 22 fields;
- one model slip desynced I-90 v2 for the rest of the run;
- the script could talk over the model.

Benchmark numbers must measure the MODEL. The 2.5-vs-3.8 comparison is
time-boxed: `gemini-live-2.5-flash-native-audio` retires on Vertex on
2026-12-13. A simulated user listens and answers what was actually asked, which
removes the script failures. Recording the model's own transcript alongside a
speech-to-text pass over its emitted audio also makes it possible to measure
what the model actually SAID, not just what it claimed it said.

## Design (the How, as approved)

- **Actor:** Claude Haiku 5.5 (`claude-haiku-5-5`) works from a persona plus a
  fact sheet (the answer key). Each turn it receives what Gemini said, as text,
  and returns ONE move under strict structured output: `{move, field_key}`.
  `move` comes from a closed enum (answer, confirm, reject and correct, spell,
  ask to repeat, persona-specific moves) and `field_key` from an enum of
  fact-sheet keys.
- **The harness renders every value, never the actor.** Words, values and
  spelled letters all come from the fact sheet through a small set of phrasings
  per move. The actor therefore cannot invent or mistype a value; "no off-sheet
  value" holds by construction.
- **Mouth:** the rendered reply goes through TTS to 16 kHz PCM. That is gTTS via
  the existing `synth_cached`, or Chirp3-HD requested as LINEAR16 16 kHz. It is
  injected inside `activity_start` / `activity_end` brackets, exactly like the
  scripted path.
- **Ears**, selectable per run:
  - (a) Gemini's output transcript, which needs the adapter transcript fix
    from bd `r3ham.6`;
  - (b) Cloud STT of the emitted audio, REQUIRED for spelling and read-back
    tests.
- **The harness owns turn-taking.** The user speaks only once ALL of these hold:
  - the generation reached turn_complete or was interrupted;
  - no tool call is pending;
  - simulated playback has ended (first-audio time plus audio duration);
  - a short quiet window has passed.

  Only an explicit barge-in persona may break this gate, and barge-in is out of
  scope here.
- **Divergence logging, always on, in either ears mode.** For every model
  generation, the run records:
  - Gemini's output transcript;
  - the Cloud STT of that generation's emitted audio;
  - a divergence score;
  - letter-level diffs for spelled values.

  One STT pass per generation serves both this log and ears mode (b). The method
  is the v2 method of `scripts/spikes/stt_readback_diff2.py`: Cloud STT v1, sync,
  `model=default`, A-Z phrase hints, one request per clip, no prompt. (The v1
  method was retracted for a priming artifact.) Per-generation PCM is captured in
  `FakeClientWebSocket.send_bytes` and sliced at the per-generation boundary the
  harness already wraps (`_dev_flush_audio_dump`).
- **Scoring stays deterministic.** The actor never grades. Each run reports two
  numbers that are never mixed:
  - `filled_confirmed`, comparable with r3ham;
  - `correct_vs_factsheet`, through the existing strict scorer
    (`score_fill_accuracy` + `W7_EXPECTED`, bd r3ham.14).

  The W-7 fact sheet carries the same Ana Reyes persona values as `W7_EXPECTED`,
  and a drift test pins the two together.
- **Kits are not in git** (CLAUDE.md scar #10). The fact sheet is keyed by field
  id, and a run fails fast if any key is missing from the loaded schema. Each run
  records the kit version or hash.

## Exit rubric

| # | Criterion | Verify |
|---|---|---|
| 1 | On W-7, a persona that does not spell names until asked fills AND confirms all 22 fields in >=1 run on `gemini-3.8-live` and >=1 run on `gemini-live-2.5-flash-native-audio`. Strict correctness against the fact sheet is reported alongside. | `summary.json` shows `filled_confirmed == 22` for one run per model, with `correct_vs_factsheet` present |
| 2 | The simulated user never speaks over the model: in every run, 0 user turns start before the gate opens (turn_complete or interrupted, no pending tool, simulated playback ended). | per-run summary `gate_violations == 0` |
| 3 | The actor cannot introduce a value that is not on the fact sheet: every value spoken in every run comes from the fact sheet. | run summary `off_sheet_values == 0`; the actor schema is a strict enum (code read plus unit test) |
| 4 | Every run records, per model generation, Gemini's output transcript, the Cloud STT of the emitted audio (v2 method), a divergence score, and letter-level diffs for spelled values. A run-level summary gives the divergent count, the rate, and the worst examples. All of it is committed under `scripts/spikes/data/sim_user/` with the persona id on every record. | open the committed per-run JSON and its summary |
| 5 | n>=3 runs per model. Per-run cost is split into Gemini Live, sidecar text, actor, TTS and STT, with mean and spread for fill and cost, in a findings doc. | the table in `scripts/spikes/sim_user_findings.md` |

## Bead tree

| Child | Writes (surfaces) | Inherits | Tier | Order |
|---|---|---|---|---|
| E.1 Actor core. The W-7 non-spelling persona and fact sheet (JSON). The strict move schema. The value renderer. Actor backends: Haiku 5.5 on Vertex, plus an offline scripted stub. Offline unit tests, including a fact-sheet vs `W7_EXPECTED` drift test. | `scripts/spikes/sim_user/` (actor, personas), `backend/tests/unit/test_sim_user_actor.py` | 3 | sonnet | parallel with E.2 |
| E.2 STT divergence scorer. Lift the v2 helpers out of `stt_readback_diff2.py` into a shared module that diff2 then imports. Per-generation scoring (transcript vs STT, divergence score, letter diffs) and a run summary. Offline tests on synthetic inputs. | `scripts/spikes/sim_user_stt.py`, `scripts/spikes/stt_readback_diff2.py`, `backend/tests/unit/test_sim_user_stt.py` | 4 | sonnet | parallel with E.1 |
| E.3 Harness integration. `--user sim --ears {transcript,stt}`. Per-generation PCM capture in `send_bytes`. The playback-aware turn gate. The TTS mouth (gTTS cache, plus Chirp3 LINEAR16). Strict scoring from the fact sheet. Cost lines for the actor, TTS and STT. Committed per-generation records. | `scripts/spikes/measure_form_session_costs.py` | 1, 2 | sonnet | after E.1 and E.2 |
| E.4 Measurement. A pilot, then n=3 runs on each of the 2 models. Findings doc and committed data. | `scripts/spikes/sim_user_findings.md`, `scripts/spikes/data/sim_user/` | 1, 5 | sonnet (+opus to read the results) | after E.3 and Haiku access |

No two children share a write surface. Every criterion is inherited by at least
one child. E.1 and E.2 can run concurrently.

## Out of scope

- Barge-in personas.
- I-90 v2 runs.
- Multilingual personas.
- Fixing bd `j9jpk`, where text injections carrying turn_complete=True cut 3.8
  off mid-sentence, or any other model-side defect the simulator surfaces. The
  simulator MEASURES these; it does not fix them.
- Any app or backend change.

## Privacy boundary

Transcripts and STT text from SYNTHETIC runs are committed, per bd memory
`synthetic-sim-run-artifacts-may-be-committed`. A synthetic run is one whose user
side is generated, and every record carries its persona id. These records do not
use the gitignored `*.debug.json` name. Anything a real human spoke into stays
local-only under `docs/standards/hipaa-pii-policy.md`: local dev with a person
talking, staging and demo, and deployed logs. Personas are synthetic only, never
real client data.

## Cost (experimentation Gate 2)

| Item | Per W-7 run |
|---|---|
| Gemini Live + sidecar (e72on n=3 W-7 happy path: 3.8 $0.905, 2.5 $0.697) | ~$0.80 |
| Actor, Haiku 5.5 (~45 turns x ~3k in / ~150 out) | ~$0.02 |
| TTS, Chirp3-HD at $30 per 1M characters (~2k characters); $0 on gTTS | ~$0.06 |
| Cloud STT v1 at $0.024/min, billed in 15 s increments (~45 generations) | ~$0.30 |
| **Total** | **~$1.20** |

That is 6 measured runs plus about 4 pilot and debug runs, roughly **$12**.
**Hard cap: $20.**

**Open dependency: access to Haiku on Vertex.** Project `polyglot-demo-aa709`
returned 429 "Quota exceeded ... base model anthropic-claude-haiku" on its first
two calls, which points to a zero default quota. This blocks E.4's live runs. It
does not block E.1 through E.3, which build and test against the offline stub
actor.
