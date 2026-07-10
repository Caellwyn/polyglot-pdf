---
date: 2026-07-09
bead: polyglot-pdf-en2j
title: "Purge the dead JIT SI mode (DTI + legacy full-SI survive)"
tags: [voice-ai, dti, si-reduction, cleanup]
---

## Trigger

The 2026-07-09 bead audit confirmed JIT lost the reduced-SI A/B and DTI is the
shipped production mode (`deploy-demo.sh` runs `USE_DTI=true,
CONTINUOUS_SESSION=true`; both SI flags default off). The service layer carried
THREE parallel field-fill SI modes (legacy full-SI, JIT manifest, DTI) as
experiment scaffolding for epic jnjj. With the cutover settled, the losing JIT
mode is dead code. en2j was blocked on the (now-closed-as-obsolete) cutover bead
jnjj.12; the audit unblocked it.

## Scope decision: JIT-only, keep legacy full-SI

A design pass mapped the deletion boundary. Verdicts:

- **JIT (`USE_JIT_SCHEMA`) -- deleted.** Pre-authorized ("JIT is dead"). Cleanly
  severable from DTI: separate SI template (`JIT_SYSTEM_INSTRUCTION` vs
  `DTI_SYSTEM_INSTRUCTION`), a distinct `if/elif/else` branch, and its own
  next-field function (`get_next_field_schema` vs DTI's `get_field_guidance`).
- **Legacy full-SI (`USE_DTI=false`) -- kept.** Deleting it is a consequence-
  bearing capability removal (it is the only non-manifest handshake path and the
  fallback when DTI is off) that would need maintainer sign-off and contradicts
  the si-reduction.md contract. NOT in the "JIT is dead" authorization. The bead's
  "reduced to a single flag if two modes survive" criterion is satisfied without
  touching legacy: after deleting `USE_JIT_SCHEMA`, only `USE_DTI` remains.

## The load-bearing distinction: transport vs SI mode

The single trap an over-eager "purge all JIT" grep would hit: the **manifest-first
handshake TRANSPORT is DTI's carrier, not the JIT SI mode.** These SURVIVE:

- the `handshake_jit` WS message type,
- the `schema["jit_mode"]` key `websocket_routes` sets,
- the `jit_mode_enabled` session-ready signal (now `= settings.USE_DTI`, was
  `USE_JIT_SCHEMA or USE_DTI`),
- the frontend's `jitModeEnabled` state + `handshake_jit` builder.

Verified against code: the frontend sends `handshake_jit` and reads
`jit_mode_enabled` to build the manifest-first handshake DTI rides on. In DTI mode
`USE_DTI=True` wins the SI-selection `if`, so a DTI client's `jit_mode` schema is
handled by the DTI branch (a state-free static SI that never reads
`schema["fields"]`) -- it never reached the deleted JIT branch. Only the
`USE_JIT_SCHEMA` SI selection died.

## What shipped

Code (net -1320 lines):
- `config.py`: removed `USE_JIT_SCHEMA` + `JIT_SYSTEM_INSTRUCTION`.
- `manifest_service.py`: removed `generate_part_manifest`, `get_next_field_schema`,
  `format_manifest_for_context`, `should_include_schema_in_response`,
  `estimate_manifest_tokens`. KEPT `_sanitize_options` (shared) + `get_field_guidance`
  (DTI).
- `ai_context.py`: removed the JIT `elif` (SI selection is now `if USE_DTI or
  schema.get("jit_mode") else legacy`). The `schema.get("jit_mode")` disjunct is
  the rollback-safety guard (originally Codex PR #229): a manifest-first schema
  arriving while `USE_DTI` is off routes to the DTI STATIC SI, not the legacy
  one-field dump -- the manifest is names-only, so the legacy dump can't be rebuilt
  from it. This preserves the DTI->legacy rollback window (a client with a stale
  persisted `jitModeEnabled` sends one more `handshake_jit` before `session_ready`
  corrects it). Caught by the Opus outer review; pinned by
  `test_jit_mode_schema_routes_to_dti_si_when_dti_off`. HONEST caveat (Opus review):
  "rollback safety" here means the SI no longer MISDESCRIBES the section as one
  field -- it does NOT make that transient session fully functional, because the
  per-field guidance injection is `USE_DTI`-gated and so does not fire when
  `USE_DTI` is off. The degradation (a static SI with no injected field guidance for
  one connect) is inherent to deleting the JIT mode, not introduced by this guard;
  the session self-corrects on the next connect once `session_ready` resets the
  client's flag. This is an unexercised path in practice (the demo runs
  `USE_DTI=true`; nothing flips it off).
- `form_filling_service.py`: removed `get_next_field_schema_for_jit`,
  `_loaded_field_ids`, the manifest_service import, the handler injection.
- `callback_handler.py`: removed the JIT `next_field_schema` drip + its response
  attach + the `send_form_update`/`_build_update_fields_response` param + the
  handler. KEPT the DTI `next_field_guidance` path.
- `websocket_routes.py`: `jit_mode_enabled` keys off `USE_DTI` only.

Tests: deleted `test_jit_schema_loading.py` + the JIT tests in
`test_manifest_service` / `test_ai_context` / `test_dti`; dropped the
`get_next_field_schema_for_jit` kwarg from `set_tool_handlers` call sites across 5
test files.

Docs: `config-deployment.md` (dropped the `USE_JIT_SCHEMA` flag row),
`si-reduction.md` (rewritten to DTI + legacy, JIT-mode rows/placeholders removed,
transport kept), `jit-schema.md` (246 lines -> a ~30-line tombstone that keeps the
transport-survives note).

## Verification

Full backend suite green (981 passed / 2 skipped, was 992; the -11 is the deleted
JIT tests). Full FE suite green (855 passed). The manifest-first transport contract
test (`test_websocket_protocol.py`) still passes (82) -- the transport is intact.

## Scar tissue

When purging a losing A/B arm, separate the **experiment mode** from the
**transport it happened to share**. Here the JIT SI *mode* was dead, but the
`handshake_jit` / `jit_mode` handshake *transport* it introduced became DTI's
carrier -- deleting it by name-association would have broken the shipped path. The
tell: a "JIT" symbol read by the DTI branch or the frontend's live handshake is
transport, not mode. Grep every candidate deletion for a DTI/continuous-session
reader before cutting.
