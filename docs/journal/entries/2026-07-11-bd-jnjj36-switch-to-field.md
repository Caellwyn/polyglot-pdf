---
date: 2026-07-11
bead: polyglot-pdf-jnjj.36
title: "Principal: add field-level navigation tool (switch_to_field) for secretary-directed jumps"
tags: [extractor, testing]
---

## Trigger

The last functional gap on the secretary branch of the SI-reduction epic
(`polyglot-pdf-jnjj`): the secretary (ask_secretary, shipped bd jnjj.45)
answers by NAMING a specific field, but the principal had only
section-level navigation (`switch_section`) -- it could not act on a
field-level answer, and had no way to jump back to correct an earlier
answer. A code audit this session confirmed the tool existed only in docs.

## What shipped

- **The `switch_to_field` tool**, mirroring skip_field's synchronous
  round-trip: declaration in `config.py` TOOL_DECLARATIONS (protocol-only
  DTI SI needs no edit -- by design), dispatch in `callback_handler`,
  `request_switch_field` in the coordinator, `switch_field` /
  `switch_field_response` wire pair routed through `websocket_routes` +
  `form_filling_service`.
- **The pin mechanism (the design core)**: the client resolves the
  identifier (field_id -> spoken_name -> name -> aliases, case-insensitive,
  WHOLE schema -- deliberately not the section-scoped lookup with the lt9z
  blind spot) and sets `pinnedFieldId` in `SchemaFormState`.
  `computeNextField` returns the pinned field first, so every existing
  "what's next" consumer -- the hint, the DTI schema drip, UI focus via
  `onNextField`, stall recovery -- follows the jump with no extra plumbing.
  The pin releases on confirm/skip, is abandoned by a section switch, and a
  pin on an already-confirmed field stays dormant until the model updates
  the value (the correction flow: update resets confirmed, the pin snaps
  in). **Fresh-eyes round 1 caught the one consumer the pin missed**:
  `isFormComplete` ignored it, so once every REQUIRED field confirmed, the
  completion-gated consumers (post-confirm hint, reconnect/manual-edit
  hints, the form-complete event) reported "complete" and silently
  abandoned a jump to an unconfirmed optional field -- exactly the
  "let me add my middle name at the end" case. Fixed at the source: a
  shared `resolveLivePin` staleness check now feeds BOTH computeNextField
  (pin = next field) and isFormComplete (live pin = not complete), with
  regression tests for the required-confirmed + optional-pin scenario.
- **Backend response semantics**: on success the ack carries the target's
  hint + (DTI) schema; the handler merges the schema (validation + the
  current-field coercion pointer) and returns rendered guidance + the
  current value (same Gemini trust boundary as get_field_value; never
  logged). Failures are fixed tokens: `unknown_field` (suggests
  ask_secretary), `hidden` (conditionally inactive), `other_section`
  (names the owning section + suggests switch_section first -- sections and
  fields stay distinct units, scar #5).
- **Headroom regression test updated**: the ~1978-token measured eviction
  floor predates the tool-set growth (ask_secretary, skip_field, now
  switch_to_field), so the stale estimator-undershoot assertion became a
  current-tools guard (window > estimated floor) alongside the unchanged
  measured-floor net.
- **ws-protocol.md** gained both wire types (the contract tests enforce the
  doc-code union -- they caught the omission, as designed).
- **Verification (exit criterion 2)**: a deterministic two-sided probe --
  the REAL WebFormConnection message dispatch driven in vitest (resolve ->
  pin -> onNextField UI focus -> ack with hint+schema) plus the REAL
  coordinator round-trip in pytest -- pins both ends of the same wire
  contract. 11 backend + 17 frontend tests.

- **Review loop outcome**: fresh-eyes (2 rounds, Sonnet find + Opus clear)
  caught the isFormComplete pin integration; the Opus outer review's
  alternating passes caught the checkbox-group `[]`-alias reads on the ack +
  pin (fixed via the shared `readFieldEntryWithAlias`) and the
  `navigateToSection` pin-clear -- four fix cycles to two independent
  NO-GAPS. Deferred nits: bd polyglot-pdf-luju; out-of-scope pre-existing
  findings filed: bd polyglot-pdf-ipw7 (computeNextField main-loop alias
  blindness).

## Lessons

- The repo's doc-as-contract gates work: the WS-protocol contract tests
  failed the full suite until the new message pair was documented -- the
  exact drift they exist to catch.
- A token-floor constant measured against a live config snapshot rots as
  the config grows (same lesson as G3's expected-canon rot, one bead
  earlier): guard against the CURRENT derived quantity, keep the measured
  constant as a lower bound.

## Doc freshness

`docs/standards/ws-protocol.md` updated + stamped 2026-07-11 (the two new
wire types). Other stale docs flagged by prep track surfaces this branch
did not touch; left as-is.

## Files touched

- `backend/config.py` -- switch_to_field TOOL_DECLARATIONS entry
- `backend/services/callback_handler.py` -- dispatch + handler
- `backend/services/request_coordinator.py` -- request_switch_field +
  response completion
- `backend/services/form_filling_service.py` -- response delegate
- `backend/routes/websocket_routes.py` -- switch_field_response routing
- `frontend/src/webFormConnection.ts` -- switch_field handler + ack
- `frontend/src/schema-forms/state/schemaFormState.ts` -- pinnedFieldId +
  resolveFieldForNavigation + pinField/clearPinnedField + pin release in
  confirm/skip/switchToSection + load migration
- `frontend/src/navigation.ts` -- computeNextField pin priority
- `backend/tests/unit/test_switch_to_field_tool.py` -- NEW
- `backend/tests/unit/test_tool_contract_static.py` -- new tool in the pins
- `backend/tests/unit/test_live_ai_gemini.py` -- headroom guard update
- `frontend/src/__tests__/switch-to-field-pin.test.ts` -- NEW (unit + E2E
  probe)
- `docs/standards/ws-protocol.md` -- wire-type tables + stamp
