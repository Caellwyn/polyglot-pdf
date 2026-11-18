---
date: 2026-11-18
bead: polyglot-pdf-ctzze
title: "sim-user E.1 + E.2: actor core and STT divergence scorer (also closes polyglot-pdf-wqnxr)"
sprint: 25
tags: [harness, testing, refactor]
---

## Trigger

Epic `polyglot-pdf-ya4vi`, plan `docs/sprint_25_sim-user_plan.md`, approved by
the maintainer 2026-11-18. The gemini-3.8-live benchmark (epic r3ham) drove
Gemini Live with fixed scripted answers. A non-spelled name stalled W-7 at
2/22, and one model slip desynced I-90 v2 for the rest of the run. So the
numbers measured how brittle the script was, not just the model.

This PR builds the two offline halves of the simulated user. They are
independent:
- E.1 (`polyglot-pdf-ctzze`): the actor;
- E.2 (`polyglot-pdf-wqnxr`): the scorer that compares what Gemini said
  against what it actually spoke.

## What shipped

- **E.1, `scripts/spikes/sim_user/`.**
  - **Persona.** A W-7 persona, `w7_ana_nospell_v1`, generated from
    `W7_QUESTIONS` / `W7_EXPECTED` so its 22 facts cannot drift from the
    strict key.
  - **Schema.** A strict `{move, field_key}` JSON schema with closed enums.
  - **Renderer.** The harness-side renderer is the only place spoken words come
    from, so an off-sheet value is impossible by construction rather than
    policed afterwards.
  - **Backends.** Two actors share one async `decide()`:
    - a deterministic `StubActor`, which runs offline and doubles as the
      fallback;
    - a `HaikuVertexActor` on `claude-haiku-5-5`. It uses `output_config`
      json_schema, thinking disabled, effort low, and no sampling parameters.
      It falls back to the stub on a refusal, bad JSON, an off-enum key, or an
      exception.
- **E.2, `scripts/spikes/sim_user_stt.py`.**
  - **Shared helpers.** The v2 Cloud STT helpers (`letters`, `words`,
    `containment`, `recognize`, the thresholds) were lifted out of
    `stt_readback_diff2.py`. diff2 now imports them as aliases.
  - **`recognize_pcm`.** Works on raw 24 kHz PCM. Clips under 0.6 s are never
    sent, and billing rounds up to 15 s.
  - **`score_generation`.** Produces a word-level divergence score, a verdict
    in diff2's vocabulary, letter-level diffs, and expected-spelling checks.
  - **`summarize_run`.** Returns counts, the divergence rate, the worst N, and
    STT cost.
  - **Equivalence check.** 15 frozen rows from the 0rpu v2 report reproduce
    their stored letters, containment and verdicts through the shared code.
- **Tests.** Offline, in `backend/tests/unit/`: 40 (actor) and 52 (STT). The
  builders mutation-verified them (scar #9):
  - renderer digit injection;
  - the `"none"` check dropped;
  - validation skipped;
  - `additionalProperties` true;
  - billing floor instead of ceil;
  - verdict thresholds;
  - pseudo-word recovery removed.

  Two mutations initially SURVIVED (the partial threshold, and PARTIAL left
  out of the divergent count). Tests were added until both went red.
- **Not verified live.** The real `AnthropicVertex` call is pinned only by an
  injected-client test. `anthropic` is not installed in the venv, and Haiku on
  Vertex currently returns a 429 for a zero base-model quota in
  polyglot-demo-aa709, which the maintainer has to raise. The live diff2 CLI
  replay also was not re-run, because it needs WAVs and STT.

## Lessons

- Spike tests belong in `backend/tests/unit/`. `pytest.ini` never collects
  anything under `scripts/` (`norecursedirs = scripts`), and the plan's first
  draft put them there. Check `testpaths` before you name a test location in a
  plan.
- The actor never chooses words. Keeping its output to `{move, field_key}` made
  "no off-sheet value" a property of the code rather than of the model, and it
  made the actor cheap.

## Doc freshness

Added `docs/sprint_25_sim-user_plan.md` and its row in `docs/INDEX.md`. No
component or standards doc tracks `scripts/spikes/`, so none needed a bump.

## Files touched

- `docs/sprint_25_sim-user_plan.md` (new), `docs/INDEX.md` (active-plan row)
- `scripts/spikes/sim_user/__init__.py`, `actor.py`, `personas/w7_ana_nospell.json` (new)
- `scripts/spikes/sim_user_stt.py` (new)
- `scripts/spikes/stt_readback_diff2.py` (now imports the shared helpers)
- `backend/tests/unit/test_sim_user_actor.py`, `test_sim_user_stt.py` (new)
