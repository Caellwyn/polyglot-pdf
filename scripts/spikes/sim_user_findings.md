# gemini-3.8-live re-measured with a simulated user (bd polyglot-pdf-15j9v)

**Date:** 2026-11-20 (UTC).

**Why:** the 3.8 benchmark of 2026-11-18 (`3p8_cost_bench_findings.md`, bd
`e72on`) drove the model with a fixed script. That user always said "yes",
never answered a spelling request, and kept reading the next line whatever
the model said. Several of its results were artifacts of that script: every
I-90 run derailed, and a wrong stored value was never corrected. This re-run
replaces the script with a simulated applicant who listens and answers. 2.5 is
not re-measured: it retires on Vertex on 2026-12-13.

**Model:** `gemini-3.8-live` on Vertex us-central1. Every run's `.meta.json`
records the model id.

**Instrument:** `scripts/spikes/measure_form_session_costs.py --user sim`.
- The applicant is a Haiku 5.5 "actor" playing a persona from a fact sheet.
- Its words are spoken through gTTS.
- It hears the model through the model's output transcript.
- A deterministic referee (bd `ya4vi.3`) overrides the actor's yes/no on a
  read-back when an exact match against the fact sheet proves it wrong.
- Cloud STT re-transcribes the model's actual output audio, so a transcript
  that differs from what was spoken is caught.

**Config (production fidelity):**
- `--arm dti --continuous --compression --derive-compression --text-ai --pro-pass`.
- `LIVE_TEMPERATURE=0.4`, `SPELLBACK_TOOL_ENABLED=true`, push-to-talk brackets.
- Input and output transcription on, session resumption off.

**Runs:** 9 benchmark runs in three groups of 3, run serially. Four more runs
are not in the benchmark, and are listed under "Discarded runs".

**Spend:** about $32.80 in all, including the discarded runs.
- Gemini Live: $24.39.
- Measurement overhead (the actor plus STT): about $7.50.
- The two runs that crashed: about $0.90.

**Raw data:** `scripts/spikes/data/sim_user/bench/` holds, per run:
- `.summary.json`, `.meta.json`, `.csv`, `.turns.csv`;
- the sim-user ledger `.sim-user.json`, with every user turn, what the actor
  heard, and each model generation's STT score.

The run index is `scripts/spikes/data/sim_user/RUNS.md`.

## Headline

Product cost is the Gemini Live spend plus the text sidecars. The actor and
STT exist only to measure, so they are excluded here and listed separately
below.

| Group (n=3) | $ / form, mean (range) | Fields correct, strict | $ / correct field | First audio p50 / p90 (local, pooled) | Turns | GoAway |
|---|---|---|---|---|---|---|
| W-7 happy | **$1.055** ($1.029-1.097) | 22, 22, 22 of 22 | $0.048 | 1.19 s / 1.36 s (n=139) | 48-49 | 2 of 3 runs |
| W-7 self-correcting (every fact slipped once) | **$1.565** ($1.394-1.719) | 22, 22, 22 of 22 | $0.071 | 1.20 s / 1.47 s (n=207) | 63-79 | 3 of 3 |
| I-90 v2 | **$3.554** ($3.275-3.873) | 55, 57, 54 of 57 | $0.064 | 1.16 s / 1.34 s (n=391) | 124-145 | 3 of 3 (3 each) |

**Every one of the 9 runs completed the form.** That is 303 of 303 fields
filled and confirmed, with no turn-cap stop and no derailment.

### Compared with the scripted 3.8 benchmark (2026-11-18)

| Group | Scripted: $ / form, correct | Sim user: $ / form, correct |
|---|---|---|
| W-7 happy | $0.905, 21/22 in every run | $1.055 (+17%), 22/22 in every run |
| W-7 with corrections | $1.709, 19-20/22 ("unhappy" script) | $1.565 (-8%), 22/22 (self-correcting persona) |
| I-90 v2 (57 questions) | all 3 runs aborted at q23-q42 | $3.554, 54-57/57, all complete |

- **W-7 happy costs 17% more with a real-shaped user, and is more accurate.**
  - The sim user answers in fuller sentences, which raises audio-in from
    $0.365 to $0.444.
  - The model speaks more, which raises audio-out from $0.059 to $0.101: it
    asks for spellings and the user answers them.
  - Text-in is almost unchanged ($0.459 vs $0.475).
  - The script's one recurring miss, `Anna` for a spelled "A-N-A", is gone.
    The user hears the stored spelling and corrects it. Scripted, that miss
    was an artifact of a user who always says yes.
- **Corrections cost about 50% more than the happy path ($1.565 vs $1.055).**
  The self-correcting user gives a plausible wrong answer for every field,
  then fixes it on the read-back. All 64 slips that were spoken were
  corrected. 2 of 66 were never spoken, because the model asked for a
  spelling first and the persona then spelled the true value. No field was
  left holding its slip.
- **I-90 now completes on 3.8.** This is the first measured full run of the
  current 57-question kit (`i-90_v2`) on 3.8.
  - The closest 2.5 reference on the same kit is $2.06 per form (bd `2nikx`,
    2026-08-28, fixed-script user). That comparison is not like-for-like:
    the user model differs, three months of code changes sit between the
    runs, and its 48/57 accuracy came from the older lenient scorer, which
    is not comparable with the strict scores here.
  - The pitch material's "about $3.2-3.5 on 3.8" was extrapolated from the
    older 113-question I-90 (2.5, $2.44-2.66). That is a different form, so
    this measurement neither confirms nor replaces it.

## Cost split by modality (thinking as its own line)

Mean $ per form, from the per-turn `token_usage` lines of each run log, at
the `GEMINI_PRICING_BY_FAMILY["3.8"]` list rates. Each run's split sums to
within 1% of its `voice_usd`. Thinking is priced at the text-output rate and
is an upper bound (see `3p8_deployed_telemetry_findings.md`).

| Line | W-7 happy | W-7 self-correcting | I-90 v2 |
|---|---|---|---|
| Text in | $0.475 (44.7%) | $0.697 (44.3%) | $1.416 (39.9%) |
| Audio in | $0.444 (41.8%) | $0.694 (44.1%) | $1.770 (49.8%) |
| Audio out | $0.101 (9.5%) | $0.122 (7.7%) | $0.252 (7.1%) |
| Thinking | $0.030 (2.8%) | $0.043 (2.7%) | $0.084 (2.4%) |
| Text out, excluding thinking | $0.012 (1.1%) | $0.018 (1.1%) | $0.032 (0.9%) |
| Thinking tokens per form | 6.6k | 9.6k | 18.6k |

- **The measured invariant holds: text-in and audio-in are the two cost
  lines, together 86-90%.**
  - Text-in leads the W-7 happy path, narrowly.
  - They are even with corrections.
  - Audio-in leads the long I-90.
- **Thinking stays at 2-3%.**
- **Text sidecars are negligible.** The secretary ran 2-5 times per I-90 for
  under $0.02, and the pro pass did not trigger.

### Measurement overhead (excluded from the product figures above)

| Group | Actor (Haiku 5.5) | Cloud STT | gTTS | Total per run |
|---|---|---|---|---|
| W-7 happy | ~$0.009 | ~$0.36 | $0 | $0.367 |
| W-7 self-correcting | ~$0.017 | ~$0.46 | $0 | $0.479 |
| I-90 v2 | ~$0.053 | ~$0.98 | $0 | $1.031 |

STT is 95% or more of the overhead. gTTS is the free endpoint and costs nothing. Billed at 15-second blocks, it is the cost of
checking every model generation's audio against its transcript.

## Latency and wall clock

- **First-audio latency** is measured from push-to-talk release to the first
  audio byte, on the LOCAL harness. The pooled p50 is 1.16-1.20 s and the p90
  1.34-1.47 s. That matches the scripted benchmark's 1.16 s / 1.34 s, so 3.8
  latency is unchanged by the user model. These are local numbers; deployed
  latency is a separate measurement.
- **Wall clock is not a product number here.** A W-7 took 660-1265 s and an
  I-90 2000-2160 s. That includes the actor's decision time, gTTS synthesis,
  STT, and the harness waiting for playback to finish. A human is not slower
  than the actor in the same way, so do not quote these.

## Session stability

- **GoAway arrives about every 10 minutes of continuous session.** There
  were 15 in all: 0-2 per W-7 and 3 per I-90. W-7 happy run 1 ran 1072 s
  with none, because its 5 unannounced drops kept restarting the session.
- **Each GoAway reconnect was clean.** Downtime was 3.1-5.3 s, and every run
  completed after up to 3 GoAway reconnects.
- **There were 8 unannounced drops.** Two runs had extra reconnects after an
  abnormal close (code 1006) or a transport error: 5 in W-7 happy run 1 and 3
  in I-90 run 3. They came on the same evening the free gTTS endpoint also
  refused connections, so a local network cause is likely. Both runs
  recovered and completed.
- **There were 0 close-1011 errors.**
- **The turn gate timed out twice in each of the two runs with drops** (W-7
  happy run 1 and I-90 run 3): the sim user waited for a reply that the
  dropped session never sent, then moved on. There were no gate timeouts in
  the other 7 runs, and no gate violations in any.

## Verdicts on the open 3.8 beads that came from the scripted runs

| Bead | Scripted finding | Sim-user verdict |
|---|---|---|
| `r3ham.9` | name with no spelling: re-asks for the spelling forever (2/22 W-7) | **Harness artifact.** Every run asked for 2-5 spellings and moved on once the user spelled. The script never spelled when asked. |
| `r3ham.10` | "same as mailing, <address>" written as an empty physical street; one field behind; I-90 desync | **Real model behavior, no longer a desync.** In all 3 I-90 runs the model said the physical street is "left blank because it is the same as your mailing address". The kit's question says "only if it is different from your mailing address", so leaving it blank follows the kit's own wording. The strict key expects the address copied. The user insisted, and the field ended correct in all 3 runs, at a cost of 3-8 extra turns. Whether blank is acceptable is a kit-wording and answer-key question for the maintainer, not a model bug. |
| `r3ham.11` | degraded session after a GoAway reconnect | **Not reproduced.** 23 reconnects (15 after a GoAway) across 9 runs, every session completed, no silent or degraded stretch after reconnecting. |
| `r3ham.13` | silent turn after get_form_status + confirm_field | **Not reproduced.** Of about 790 model generations, 21 had no audio, and all 21 are the designed silence while the `name_spellback` clip plays. There were 0 unexpected silent turns. |
| `r3ham.15` | spelled-name VALUE wrong (JOSE -> JOSHUA ...) | **Not seen in these personas.** Every spelled name was stored correctly at the end. The user hears the clip and corrects a wrong spelling. |
| `r3ham.16` | I-90 tool-silent at the first Part 3 question | **Not reproduced** in 3 I-90 runs. |

These beads stay open, and the verdicts are evidence for whoever picks them
up; closing a bead is its own decision.

## New defects found (filed)

- **`r3ham.23`: the model spoke an internal instruction aloud.**
  - Once in 45 `name_spellback` deliveries (I-90 run 2), the model voiced the
    tool response's text: "The user has already heard the stored spelling...
    stay silent and listen for their yes or no."
  - Its output transcript for that generation was empty. Only the STT check
    caught it.
  - A real user would hear it.
- **`r3ham.24`: wrong stored values confirmed.** 3 substantive wrong values
  in the 171 I-90 fields (303 fields across all 9 runs), all on I-90:
  - **Mobile phone.** The user said "...0297". The model stored 0197. On the
    third read-back its transcript said 0297 while its AUDIO said 0184 (the
    daytime number). The actor hears the transcript, so it confirmed.
  - **Physical ZIP.** The user said 97203. The model read back 97203,
    re-asked, then stored and read back 90210, a value nobody said. The actor
    rejected it, but the first referee build overrode the rejection (bug
    below, now fixed). Whether the model would have self-corrected is
    unknown.
  - **Port of entry.** The user said "Portland, Oregon" three times. The
    model stored "Portland International Airport, Oregon", and it was
    confirmed.
  - Plus 2 **format-only** misses: `country_of_birth` stored as "the
    Philippines" for "Philippines", because the user said "the Philippines".

## Harness defects found during the re-run (fixed before these numbers)

- **The actor misjudged read-backs, both ways (fixed: bd `ya4vi.3`).** In the
  first pilot I-90, the actor rejected a correct "C, O, R, A, Z, O, N" 20
  times and hit the turn cap. In the first pilot self-correcting W-7, it
  confirmed a slipped "Lucy". The deterministic referee now overrides only on
  an exact match against the fact sheet.
  - In the 6 runs on the referee build it fired 14 times. A hand audit found
    13 right.
  - The wrong one was the ZIP above: two read-backs in one heard window, with
    the right value in the first. The referee now stays out of any window
    that holds more than one read-back. Replaying every run under the fixed
    rule keeps the 13 right overrides, drops the wrong one, and adds none.
  - The W-7 happy group ran before the referee existed. Replaying its ledgers
    shows 2 actor false rejects, each costing one extra read-back turn and no
    accuracy. That group is kept as is.
- **gTTS refused a connection mid-session (fixed: bd `ya4vi.5`).** Two
  self-correcting W-7 runs died partway through and were re-run. Synthesis
  now retries with backoff.

## Discarded runs

| Run | Why discarded |
|---|---|
| `costs_w7_..._20261120T193947Z` (W-7 self-correcting pilot) | Pre-referee; the actor confirmed a slip ("Lucy"), so 21/22 was the actor's error. |
| `costs_i90-v2_..._20261120T200124Z` (I-90 pilot) | Pre-referee; the actor rejected a correct spelling 20 times and the run hit the turn cap at 54/57. |
| two W-7 self-correcting runs at 21:23Z and 21:28Z | Crashed on a transient gTTS connection refusal at turn ~13 and ~27; no summary written. |

## Caveats

- **The user is simulated.** Its speech is gTTS, and it hears the model's
  transcript, not its audio. A transcript-vs-audio mismatch (r3ham.24) can
  therefore pass the actor. The STT score records each one.
- **n=3 per group.** The W-7 ranges are tight ($0.07 and $0.33). The I-90
  range is $0.60, driven by how many correction turns a run needed.
- **Local harness.** Latency is local. Cost and token figures are model-side.
- **One self-correcting persona and one I-90 persona.** Other answer styles,
  languages and forms are not covered here.
