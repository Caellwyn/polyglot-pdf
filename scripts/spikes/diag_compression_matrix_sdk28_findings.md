# Compression support matrix on SDK 2.8.0: findings (bd polyglot-pdf-h04c)

*Date: 2026-06-12. Epic: polyglot-pdf-hcsl (sprint 4). Data:
`diag_compression_matrix_sdk28_runs.jsonl` (51 live sessions, single day --
the planned day-2 calendar repetition was DROPPED by maintainer decision
2026-06-12: the failure classification is configuration-based, not time-based,
so a second day adds nothing; rubric change logged on the epic bead).*

## Verdicts

1. **Sliding-window eviction works on BOTH model tiers under google-genai 2.8.0**
   (api_version `v1beta`, the SDK default -- confirmed in every record).
   - **3.1** (`gemini-3.1-flash-live-preview`): 3/3 twenty-turn on-live runs
     evicted, 3-4 drops each (e.g. 2085->1094, 2207->769), oscillating ~1.0-2.2k
     vs the off-arm compounding to ~5-6k. Replicates
     `eycd_compression_eviction_findings.md` (3/3 independent runs).
   - **2.5** (`gemini-2.5-flash-native-audio-preview-12-2025`): 3/3 twenty-turn
     on-live runs evicted (WITH production tools -- see verdict 2), 2-3 drops each
     (3336->2397, 3191->2095, 3393->2451), oscillating ~2.1-3.4k vs the off-arm
     compounding to ~6.5k.
2. **The 2.5 "1011 instability" was OUR PROBE'S CONFIGURATION, not Google and not
   compression.** Any probe passing `tool_declarations=None` dies with
   `1011 Internal error` after turn 1; passing the production `TOOL_DECLARATIONS`
   makes 2.5 stable. Prior "transient server-side" framings (bd `daa`, the eycd
   findings' "2.5 untestable") trace to this artifact: every minimal probe omitted
   tools; production always passes them, which is why demo traffic was clean while
   probes crashed.
3. **Eviction is asynchronous**: the prompt-token drop lands 1-3 turns after
   crossing `trigger_tokens`; 10-turn probes under-detect (0/5 here, 2/3 in the
   eycd series); 20-turn probes detect 100%. Landing zone sits ABOVE
   `target_tokens` by roughly the unevictable base (SI + tool declarations:
   with-tools base ~1,137 tokens -> post-eviction floor ~2.1-2.5k against an
   800 target). The signal is the `prompt_token_count` drop;
   `cached_content_token_count` stays `None` always.

## The matrix (all cells, 2026-06-12)

Configs: `off` (control), `on-inert` (trigger=100k, can never fire),
`on-live` (trigger=1500, window=800). "died" = session lost to an error.

| model | config | tools | turns | runs | completed | evicted | died | error |
|---|---|---|---|---|---|---|---|---|
| 2.5 | off | none | 10 | 5 | 0 | -- | 5 | 1011 after turn 1 |
| 2.5 | on-inert | none | 10 | 5 | 1 | -- | 4 | 1011 after turn 1 |
| 2.5 | on-live | none | 10 | 5 | 0 | 0 | 5 | 1011 after turn 1 |
| 2.5 | off | none, v1alpha | 6 | 3 | 0 | -- | 3 | 1011 after turn 1 |
| 2.5-latest alias | off | none | 6 | 3 | 0 | -- | 3 | 1008 not-supported x2, 1011 x1 |
| 2.5-0925 alias | off | none | 6 | 3 | 0 | -- | 3 | 1011 after turn 1 |
| 2.5 | off | **real** | 6 | 3 | 3 | -- | 0 | -- |
| 2.5 | off | **real** | 20 | 3 | 2 | -- | 1 | 1008 at turn 9 (1 of 6 with-tools) |
| 2.5 | on-live | **real** | 20 | 3 | 3 | **3/3** | 0 | -- |
| 3.1 | off | none | 10 | 5 | 4 | -- | 0 | -- |
| 3.1 | on-inert | none | 10 | 5 | 5 | 0 (correct) | 0 | -- |
| 3.1 | on-live | none | 10 | 5 | 5 | 0 (runway artifact) | 0 | -- |
| 3.1 | on-live | none | 20 | 3 | 3 | **3/3** | 0 | -- |

## Why the 2.5 classification is "our config", with the control logic

- **Not compression:** failures are IDENTICAL across off / on-inert / on-live --
  the OFF arm has no compression config at all and dies the same way.
- **Not api routing:** identical on `v1alpha`; the `-09-2025` alias dies
  identically; `-latest` is mostly `1008` not-supported (string likely invalid).
- **Not time-of-day/transient:** within the same hour, the same model with the
  production tool declarations ran 6/6 clean short sessions and 5/6 clean
  20-turn sessions, including 3/3 with active compression. A server-side outage
  does not respect a client-side config flag.
- The one residual: **~1/6 with-tools 2.5 runs hit a mid-session `1008`**
  ("operation not implemented/supported") -- rate to watch during the phase-2
  measurement runs (bd `wyhh`), not a blocker.

## Standing consequences (recorded where they bind)

- **Deploy-fidelity rule** (maintainer, 2026-06-12): probes always mirror the
  deploy config -- production tool declarations, real SI path, realistic content.
  Rule of record: `docs/standards/testing.md` ("Live-endpoint probes and
  spikes"); bd memories `live-probes-must-mirror-deploy-config`,
  `gemini-2p5-1011-needs-tool-declarations`.
- Current-state doc: `docs/components/context-compression.md` (status banner +
  "How eviction actually behaves").
- Known gap accepted at gate-close: 3.1 WITH tools was not probed (day-1 3.1
  cells predate the fidelity rule). The phase-2 measurement (bd `wyhh`) runs
  deploy-fidelity on both models and will surface any 3.1-with-tools surprise.
- Open micro-question (untested, low stakes): whether `tool_declarations=[]`
  (empty list) also crashes 2.5, vs only the omitted-key/None form.

## Reproduce

```
backend/.venv/Scripts/python.exe scripts/spikes/diag_compression_matrix_sdk28.py \
    --models 2.5,3.1 --configs off,on-inert,on-live --repeats 5 --turns 20 --tools real
```

20 turns minimum (async eviction lag); `--tools real` always (deploy fidelity);
per-run records append to `diag_compression_matrix_sdk28_runs.jsonl`.
