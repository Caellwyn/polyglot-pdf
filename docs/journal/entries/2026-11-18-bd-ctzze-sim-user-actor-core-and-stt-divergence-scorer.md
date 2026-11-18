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
- **Haiku via the Claude API only (maintainer decision, same day).**
  - **What changed.** `HaikuActor` calls `anthropic.Anthropic()` with
    ANTHROPIC_API_KEY, which spends Anthropic credits. The Vertex path was
    REMOVED rather than left selectable, because Vertex bills the maintainer's
    Google pay-as-you-go account.
  - **Pins.** Two tests pin this, both mutation-verified:
    - a missing key raises at construction;
    - the module constructs no Vertex client.
  - **Live check.** The smoke test made two API calls, at about $0.0003 in
    total:
    - "What is your first name?" gave `answer`;
    - "Could you spell it?" gave `spell`, rendered as "A - N - A".

    There was no fallback, and the prompt cache hit on turn 2.
  - **Dependency.** `anthropic` 2.10.0 is installed in the backend venv. It is
    spike-only, so it is in no requirements file.
- **Not verified live.** The diff2 CLI replay was not re-run, because it needs WAVs and STT.

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
