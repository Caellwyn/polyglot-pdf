---
date: 2026-10-22
bead: polyglot-pdf-bd1zs
title: "feat(models): migrate lite text tier to gemini-3.1-flash-lite and standard voice to gemini-3.8-live (Vertex-verified)"
tags: [testing, security]
---

## Trigger

Maintainer request (2026-10-21): Google is retiring the Gemini 2.5 models, so
move the cheap text tier 2.5-flash-lite -> 3.1-flash-lite and the voice model
2.5 Live -> 3.8 Live. Verify availability on Vertex, update the cost tables and
docs, and test against the real systems. (The first ask said "2.5 flash ->
3.1 flash". No plain `gemini-3.1-flash` exists, and the deprecations page lists
no shutdown date for 2.5 Flash, only restricted access for new projects. The
maintainer clarified that they meant flash-lite.)

## What shipped

**Measured on Vertex first** (project polyglot-demo-aa709), with each claim
checked against the endpoint:
- `gemini-3.8-live`: Live connects at `us-central1` and returns `1008` at `global`.
- `gemini-3.1-flash-lite` / `gemini-3.5-flash-lite`: `404` at `us-central1`, OK at
  `global`. `gemini-2.5-pro` works at both.
- A probe arm sent today's exact config to 3.8 and got `1007`. The cause was
  the 2.5-only `thinking_config`, because `model_family()` mapped the unknown id
  to "2.5". **Every 3.8 session would have failed to connect.**
- 3.8 defaults tools to `NON_BLOCKING`. Unmarked, it called `update_form_fields`
  and then **ended the turn silently**. With `behavior: BLOCKING` it waited (zero
  audio during a 3 s delayed response) and then spoke.
- 3.8 always reasons. `thoughts_token_count` arrives outside
  `response_tokens_details`, and neither cost meter billed it.

**Code:**
- **Model ids:** the standard Live constants are now `gemini-3.8-live`.
  `MODEL_LABELING` and `TRANSLATION_VERIFY_BT_MODEL` default to
  `gemini-3.1-flash-lite`. `MODEL_LABELING` had defaulted to full
  `gemini-2.5-flash`, and no deploy channel pinned it, so production
  secretary/validator calls were running on full Flash.
- **Text endpoint:** `TextAIGemini.DEFAULT_VERTEX_LOCATION="global"`, and the
  outage fallback is now `gemini-3.5-flash-lite`.
- **3.8 tool behavior:** `BLOCKING` is set on every tool declaration for the
  3.8 family.
- **Pricing fallback:** `DEFAULT_PRICING_FAMILY` moved 2.5 -> 3.8, which closes
  the thinking-gate hole for unknown model ids.
- **Rate tables:** a new "3.8" Live rate row, plus two text rows. All rates
  were re-verified against the pricing page.
- **Cost meters:** thought tokens are now billed as text output in both
  meters. The Live meter feeds the spend ceiling. The text meter also fixes
  a latent under-count on the 2.5-pro validator's thinking budget.

**Verification:**
- Full suite: 6,762 passed.
- 12/12 mutation checks went red, one for each new behavior.
- The external Live contract test passed on Vertex 3.8.
- Real secretary + validator calls on Vertex 3.1-flash-lite succeeded, and
  the validator caught a ZIP/state contradiction.
- Voice-harness E2E fill/confirm/advance passed 3/3 on Vertex 3.8 in the real
  local app. The backend logged `thoughts_tokens: 224` on the opening turn,
  which would have been about 13% of that turn's cost unbilled.

**Review:**
- **Fresh-eyes (Sonnet), 2 rounds.** Round 1 found 3 stale "default 2.5"
  claims, and a mechanical sweep found 2 more. All 5 were adopted. One
  finding, a thought double-count on 3.1, was rejected: the usage contract
  is total = prompt + response + thoughts, which matched the measured
  numbers exactly. Round 2 returned NO-GAPS.
- **Opus cross-surface, 1 round, GAPS-FOUND (2).** It found two wrong tier-2
  sentences, both adopted:
  - the logging-and-cost prediction that "audio-in leads" would hold on 3.8
    (the doc's own table implies it likely flips);
  - the ai-models claim that every `TextAIGemini` takes the default location
    (two authoring scripts pass `us-central1`).
  It also filed a processing-location flag (`bsq6y`, below) and a
  mislabelled-spike bead (`uzecd`).

**Deferred, all filed:**
- `j9jpk`: on 3.8, `turn_complete` interrupts speech mid-sentence.
- `e72on`: re-measure the cost split and compression eviction on 3.8.
- `nwnys`: `scripts/bakeoff` drops thinking tokens.
- `u0kcc`: secretary/validator recall on 3.1-flash-lite.
- `crq4y`: the editor guidance-judge still uses 2.5-flash.
- `uzecd`: spikes label 3.8 runs as "2.5".
- `bsq6y`: the `global` endpoint has no regional data-residency commitment.
  This is the maintainer's call.

The rubric was written at creation; scorecard: 1 PASS, 2 PASS, 3 PASS.

## Lessons

- **A plausible model id is not evidence of availability, at any location.**
  The 3.x lite models exist on Vertex but only at `global`. The fallback chain
  already listed `gemini-3.1-flash-lite` at `us-central1`, where it had been
  404ing. Verify a model at the location the adapter actually uses.
- **A pricing helper's fallback was silently a capability gate.**
  `model_family()` returns a default family for unknown names, and the Live
  adapter keyed `thinking_config` on that family. A pricing default therefore
  decided which wire fields a new model received. Anything gating behavior on
  a lookup with a fallback inherits the fallback's choice.
- **Read the whole usage object.** `thoughts_token_count` sits outside the
  per-modality breakdowns that both meters summed, so no model with thinking
  on was fully billed.

## Doc freshness

- **Prose updated (current state):** ai-models.md (rewritten),
  logging-and-cost.md, voice-ai.md, validation-delegation.md,
  config-deployment.md, context-compression.md, security-posture.md,
  technical_guide.md, README.md, the run-local and voice-harness SKILL.md
  files, and the voice-harness RUNBOOK.
- **Stamps:**
  - config-deployment.md and security-posture.md each had a single stamp,
    which was replaced. Their old facts still live in the body.
  - voice-ai.md's stamp was replaced, and its old fact is in the body.
  - logging-and-cost.md was left at its 6 pre-existing stacked stamps,
    rather than adding a 7th.
  - validation-delegation.md is deliberately NOT bumped, to keep its bd 6dn2n
    staleness signal.
  - context-compression.md's stamp carries measured figures and was left;
    only one sentence changed.
  - technical_guide.md got prose only.
- **Reviewed and left:** other docs that track `config.py` or the Live
  adapter (jit-schema, tool-call-flow, hipaa-pii-policy, risk-rating,
  schema-key-visibility, section-reset-deprecation, si-reduction,
  voice-and-vad) were already stale from 2026-09-23 changes. Two repo-wide
  sweeps found no model claims in them that this change made wrong.
- **Not edited:** `CLAUDE.md:73`'s "on 2.5 production config" still describes
  where the cost invariant was MEASURED.
- **Unrelated:** the stale in-progress bead `h06sv` (beads GCS cut-over) was
  left untouched.

## Files touched

- backend/config.py: Live/text model defaults, the 3.8 rate row,
  DEFAULT_PRICING_FAMILY, and the text pricing rows
- backend/adapters/live_ai_gemini.py: default model, BLOCKING on 3.8, the
  thinking-gate comment, and thought tokens billed
- backend/adapters/text_ai_gemini.py: default model, `global` location, the
  3.5-lite fallback, and thought tokens billed
- backend/dependencies.py, backend/services/secretary_context.py: comments
- backend/tests/: test_text_ai_fallback, unit/test_live_ai_gemini,
  test_model_selection, test_pricing_tables, test_send_text_turn_model_branch,
  test_text_ai_gemini, test_usage_event_live_plumbing,
  test_usage_event_text_tts, contract/test_tool_contracts;
  tests/test_pricing.py
- scripts/dev-local.ps1, scripts/dev-local.sh: help text
- Docs: the files listed under Doc freshness above
