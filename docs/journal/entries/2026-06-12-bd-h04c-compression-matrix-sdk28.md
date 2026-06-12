---
date: 2026-06-12
bead: polyglot-pdf-h04c
title: "Compression diagnosis matrix on SDK 2.8 (2.5 + 3.1) + context-compression.md banner update"
sprint: 4
tags: [testing, postmortem, conventions]
---

## Trigger

First bead of the sprint-4 epic `polyglot-pdf-hcsl`
(`docs/sprint_4_sliding-window-context_plan.md`). A post-SDK-cutover probe (bd
`eycd`, 2026-06-11) found Gemini Live sliding-window eviction -- a proven no-op
on 2026-06-04 (bd `l3a.1`, SDK 1.38.0) -- suddenly working on 3.1, with 2.5
dying on `1011` errors of unknown cause. This bead's job: a controlled support
matrix on SDK 2.8.0 (per model: does eviction occur, and what is the 2.5
failure -- transient server / compression-triggered / our bug), then fix the
stale DEAD END story in `docs/components/context-compression.md`.

## What shipped

- **Probe verdict-logic fix** (`scripts/spikes/diag_compression_usage.py`): the
  l3a.1-era verdict keyed on `cached_content_token_count`, which stays `None`
  even while eviction works; the real signal is a turn-over-turn
  `prompt_token_count` DROP. This measurement artifact was part of why the
  original dead-end verdict stuck.
- **Matrix harness** (`scripts/spikes/diag_compression_matrix_sdk28.py`): per
  model x {off / on-inert (trigger can never fire) / on-live} x N repeats, with
  a logger-tap that captures every close reason without touching adapter code,
  async-eviction runway accounting (`post_cross_turns`; short-runway
  non-evictions report as inconclusive), and 2.5-classification cells
  (`--tools real`, `--api-version`, model-alias tiers).
- **51 live sessions -> two verdicts**
  (`scripts/spikes/diag_compression_matrix_sdk28_findings.md`):
  (1) **eviction works on BOTH models** under genai 2.8.0/v1beta -- 3.1: 3/3
  twenty-turn runs (plus eycd's independent 3/3); 2.5: 3/3 twenty-turn runs
  once the probe passes production tools. (2) **The 2.5 "1011 instability" was
  our probe's config**: `tool_declarations=None` kills 2.5 after turn 1
  identically across all compression arms, api versions, and the `-0925` alias;
  with production tool declarations 2.5 is stable. The OFF control arm is what
  separated this from "compression breaks 2.5"; the same-hour with-tools
  stability is what killed "transient server-side".
- **`docs/components/context-compression.md` heavy revamp** (maintainer
  directive): DEAD END banner replaced with the per-model working verdict; the
  false "we never built a cost-motivated context-bounding restart" claim
  corrected -- section resets and artificial section chopping ARE deliberate
  token-cost mitigation (maintainer: ~USD 7 unmitigated 150-question I-90), so
  the doc now frames the decision as sliding-window VS section resets; new
  measured-behavior section (async eviction, 1-3 turn lag, landing zone above
  target, incremental drops).
- **Deploy-fidelity rule** (maintainer directive): probes always mirror the
  deploy config; phase-2 measurements use real system instructions + realistic
  content. Recorded in `docs/standards/testing.md` ("Live-endpoint probes and
  spikes"), the sprint-4 plan constraints, beads `4loz`/`wyhh` notes, and bd
  memories (`live-probes-must-mirror-deploy-config`,
  `gemini-2p5-1011-needs-tool-declarations`).
- **Rubric amendment** (logged on epic `hcsl`): the maintainer dropped exit
  criterion 1's "x 2 separate days" matrix repetition once the classification
  proved configuration-based, not time-based, and gave the go to proceed -- the
  bead's escalation gate resolved in-session.
- **Filed:** bd `polyglot-pdf-3v5m` (maintainer's design idea: default to 2.5
  for latency, fail over mid-session to 3.1 on a 1011, rehydrating from client
  state). Known gap accepted at gate-close: 3.1-with-tools was not probed
  (day-1 3.1 cells predate the fidelity rule); the deploy-fidelity phase-2 runs
  (bd `wyhh`) cover it. Residual watch item: ~1/6 with-tools 2.5 runs hit a
  mid-session `1008`.
- **Fresh-eyes:** this entry is written pre-loop; the rounds/triage outcome is
  recorded in the merge ping. Codex credits remain exhausted (0 Codex comments
  on today's merged PR #166), so the fresh-eyes `NO-GAPS` verdict is this PR's
  review record.

## Lessons

- **A probe that does not mirror the deploy config is a different system.**
  `tool_declarations=None` produced a week of false "2.5 is unstable /
  transient server-side" verdicts (bd `daa` framing, eycd's "2.5 untestable")
  while the deploy-shaped config was stable the whole time. Generalized into
  `docs/standards/testing.md` and bd memory
  `live-probes-must-mirror-deploy-config`.
- **Control arms are what turn anecdotes into classifications.** The
  compression-OFF arm falsified "compression crashes 2.5" in one sweep; the
  same-hour with-tools cells falsified "transient outage". Neither follows from
  any number of on-arm repetitions alone.
- **Server-side features can be asynchronous; instrument for lag.** Eviction
  lands 1-3 turns after the trigger crossing -- 10-turn probes under-detected
  (0/5, 2/3) and nearly produced a false "still a no-op" verdict on day 1;
  20-turn probes detect 3/3. Verdict logic must distinguish "no eviction" from
  "insufficient runway".
- **Why something exists is maintainer knowledge, not code archaeology.** The
  pre-revamp doc inferred "section restarts are UX, not cost-bounding" from
  reading the code; the maintainer's actual cost history says the opposite. bd
  memory `section-resets-are-cost-mitigation` flags that bd `7kp`'s closure and
  some journal entries still carry the wrong inference.

## Doc freshness

- Bumped with content: `docs/components/context-compression.md` (full revamp,
  twice in-session as the 2.5 verdict landed), `docs/standards/testing.md`
  (deploy-fidelity section), `docs/sprint_4_sliding-window-context_plan.md`
  (new; fidelity constraint + rubric amendment), `docs/INDEX.md` (sprint-4 row).
- The closeout freshness checker flags ~10 docs (auth, schema-forms,
  tool-call-flow, ai-models, confirmation-and-audit, hipaa-pii-policy,
  logging-and-cost, risk-rating, stateless-architecture, terminology) as stale
  against backend/frontend files dated 2026-06-11 -- those are sprint-3 changes
  already on `dev`; this branch touches no runtime code, so they were stale
  before this branch existed and are left for the owning work (the sprint-3
  closeout entry records reviewing most of them).

## Files touched

- `scripts/spikes/diag_compression_usage.py` -- verdict-logic fix (drop signal)
- `scripts/spikes/diag_compression_matrix_sdk28.py` (new) -- matrix harness
- `scripts/spikes/diag_compression_matrix_sdk28_runs.jsonl` (new) -- 51 per-run
  records (curves, drops, error payloads)
- `scripts/spikes/diag_compression_matrix_sdk28_findings.md` (new) -- verdicts
- `scripts/spikes/eycd_compression_eviction_findings.md` + `eycd_*.json` (new
  here) -- the other session's bd-eycd evidence, committed so the docs' cited
  numbers have in-repo backing (fresh-eyes round-1 finding)
- `docs/components/context-compression.md` -- revamp + status flip
- `docs/standards/testing.md` -- deploy-fidelity rule
- `docs/sprint_4_sliding-window-context_plan.md` (new) + `docs/INDEX.md` --
  epic plan of record
- `docs/journal/entries/2026-06-12-bd-h04c-compression-matrix-sdk28.md` (this)
