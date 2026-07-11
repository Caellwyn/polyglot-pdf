---
date: 2026-07-11
bead: polyglot-pdf-whid
title: "Validator correction-loop audit: the loop is closed (reasons reach the voice model); four gaps filed"
tags: [extractor, conventions]
---

## Trigger

Maintainer ask (2026-07-10, filed while designing the validator decoupling):
map how the cheap-model validator's verdict actually flows back into the live
session today -- does it produce a re-review list with reasons, what does the
app do with it, what context does the voice model get, and where does the
result live given the stateless backend. This audit is the current-state map
the sprint-11 continuous-DTI epic (`polyglot-pdf-fc7t`, esp. the
validator->switch_to_field rail bead `polyglot-pdf-oiok`) builds on.

## Answers (verified against code, key hops re-read by the orchestrator)

**1. What the validator returns: a structured conflict list with per-field
reasons -- not pass/fail.** Verdict shape `{"conflicts": [{"field_ids":
[...], "reason": "<short>"}]}` (prompt contract
`backend/services/validator_service.py:60-78`; sanitize `:119-137`;
fail-open to empty on any error `:153-212`). Model call:
`TextAIGemini.validate()` (`backend/adapters/text_ai_gemini.py:148-214`),
lite-tier fallback chain, JSON-forced. The validator and the secretary share
the `ITextAI` port / `TextAIGemini` adapter / `MODEL_LABELING` knob but are
otherwise separate paths (`validate()` vs `ask()`).

**2. What happens with the result: it goes two places, and is not dropped.**
Trigger: the CLIENT proactively emits `section_complete` (confirm handler,
`frontend/src/webFormConnection.ts:1772`; skip path `:1943`) and
`form_complete` (`:2342`) with the contract-2 fields payload. Backend
(`backend/routes/websocket_routes.py:689-734`) runs
`handle_validation_boundary` (`backend/services/form_filling_service.py:
1468-1527`): suppress conflicts on already-steered fields
(`_suppress_already_steered:1529`), inject a steer into the LIVE session for
the survivors (`_inject_validator_steer:1559`), and return the delivered
conflicts to the client as a `validation_result` envelope. Client
(`webFormConnection.ts:2204-2225`): clean -> resume the PARKED section
switch; conflict -> mark fields `steered` + cancel the switch, holding the
user in-section so the voice steer can play out. The section auto-advance is
gated on this round-trip (parked in `proceedSectionSwitch:2096`, 6s
fail-open `VALIDATOR_GATE_TIMEOUT_MS`, backend-side 4s
`VALIDATOR_TIMEOUT_SEC`).

**3. What the voice model gets: the full reason text, not a cold re-ask.**
`_compose_validator_steer` (`form_filling_service.py:1593-1620`) injects
"VALIDATOR FINDING (second-pass check)..." + per conflict `- Fields:
{names}. {reason}` (the model's reason verbatim, ids mapped to field names)
+ the user-override escape hatch ("accept if they confirm both are
intentional"). Injected via `send_client_content` -- in-band to Gemini only;
deliberately never logged and never sent to the browser (no-PII rule).

**4. Where it lives: only the boolean `steered` marker, client-side.**
`markFieldsSteered` (`frontend/src/schema-forms/state/schemaFormState.ts:
1103`) persists to sessionStorage; deliberately carried forward on edits
(`:239-273`); rides the next contract-2 payload (`buildValidatorFields`,
`webFormConnection.ts:2308`) so the stateless backend re-suppresses after
reconnect. The REASON text is transient by design.

The tier-2 doc (`docs/standards/validation-delegation.md`) agrees with the
code on all six frozen contracts; only cosmetic drift (a couple of stale
line refs, B4-era narrative phrasing) -- left as-is.

## Gaps filed (one bead each, per the exit criteria)

1. `polyglot-pdf-gsae` -- no visible UI surface for validator findings: no
   re-review queue, badge, or highlight; the voice steer is the only
   surfacing, re-review is implicit hold-in-section. Direct input to the
   wt6w decoupling plan (queued corrections need a queue surface).
2. `polyglot-pdf-lt0y` -- `steered` is permanent per-field suppression:
   editing a steered field never re-arms validation, so a NEW contradiction
   introduced by an edit to an adjudicated field is never re-flagged
   (documented trade-off; bead is the decide-point on re-arming).
3. `polyglot-pdf-qnnh` -- `form_complete` conflicts cannot gate submission:
   the steer may be voiced into a dying session and the filled PDF can ship
   with the contradiction. Extra weight under sprint 11: until wt6w,
   form_complete is continuous mode's ONLY validator trigger.
4. `polyglot-pdf-ltya` -- the reason text is single-shot: a failed injection
   reads as clean (fail-open) and the reason is lost; after reconnect only
   the boolean survives. Relevant to the oiok read-back rail, which depends
   on the reason reaching the model.

## Lessons

- The maintainer's mental model ("does the app pop focus back and work down
  a list?") and the implementation ("hold the section, let the voice model
  steer") describe different UX for the same loop -- the audit's value was
  naming that delta precisely rather than building anything.
- Sprint 11's correction rail (oiok) reuses this exact plumbing; the gaps
  above are the edges of that rail, not new machinery.

## Doc freshness

- `validation-delegation.md` reviewed against code: contracts accurate,
  cosmetic drift only -- left untouched (noted here per the freshness
  protocol). No other doc tracks this surface.

## Files touched

- this journal entry only (read-only audit; gap beads filed in the tracker)
