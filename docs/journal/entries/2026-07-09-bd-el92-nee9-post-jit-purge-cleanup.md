---
date: 2026-07-09
bead: polyglot-pdf-el92
title: "Post-JIT-purge cleanup: dead cost-spike scenarios + transport-naming (el92 + nee9)"
tags: [cleanup, dti, si-reduction, ws-protocol]
---

## Trigger

Two follow-up beads filed by the en2j (JIT SI-mode purge) reviewers, closed
together as one small cleanup PR:

- **polyglot-pdf-el92**: two manual cost-spike scripts still constructed
  `Settings(USE_JIT_SCHEMA=...)`. Since en2j removed that flag (pydantic
  `extra="ignore"`), the override became a silent no-op -- so the scripts measured
  the legacy full-SI while labeling the output "jit"/"section-reset-jit",
  producing mislabeled cost data with no error.
- **polyglot-pdf-nee9**: residual "JIT mode"-as-transport naming confusion in four
  current-state locations -- comments/docs that conflated the removed JIT SI mode
  with the still-live manifest-first handshake TRANSPORT that DTI rides on.

## el92 -- the dead cost scenarios fail loudly / go honest

- `scripts/spikes/measure_form_session_costs.py`: the `--arm section-reset-jit`
  branch now raises a clear `SystemExit` ("JIT SI mode was deleted; use --arm dti
  or --arm section-reset") instead of silently applying a no-op `USE_JIT_SCHEMA`
  override and mislabeling the run. (The exit-criterion's "fail loudly" option --
  chosen over untangling the arm from ~12 shared branch sites.)
- `scripts/spikes/cost_matrix_lib.py`: `recompute_si_scenarios()` no longer patches
  `USE_JIT_SCHEMA`; its `_si_len` builds only the surviving legacy full-SI. The
  `jit` scenario returns the FROZEN historical literal (no longer live-computable),
  so the notebook's drift-check reports an honest 0 for `jit` instead of a false 0
  from a legacy-vs-legacy comparison, and the historical full/jit/drip analysis
  narrative still renders.

## nee9 -- transport vs SI mode, named correctly

The `handshake_jit` message type / `schema["jit_mode"]` key / `jit_mode_enabled`
signal / frontend `jitModeEnabled` are the manifest-first TRANSPORT (DTI's
carrier), NOT the removed JIT SI mode. Corrected the current-state surfaces that
conflated them:

- `frontend/src/schema-forms/state/schemaFormState.ts`: `setJitMode` JSDoc no
  longer says "based on backend USE_JIT_SCHEMA flag" (the gate is now
  `session_ready.jit_mode_enabled = USE_DTI`).
- `backend/routes/websocket_routes.py`: the handshake-extraction comments name the
  manifest-first transport (DTI's carrier), not "JIT mode"/"the JIT SI."
- `docs/standards/ws-protocol.md`: the mode-selector row, the `### JIT-mode keys`
  table (renamed `### Manifest-first transport keys`), and the stale SI-placeholder
  references (`{manifest_text}`/`{next_field_schema}`/"the JIT SI's {form_title}")
  corrected to the transport framing.
- `backend/tests/contract/test_websocket_protocol.py`: `doc_handshake_jit_keys()`
  looks the table up by its `###` heading -- updated in lockstep with the doc
  rename so the wire-contract test stays green (a doc-code coupling that would
  otherwise have gone red in CI).
- `token-monitor/README.md`: the "How to Monitor JIT Impact" section now targets
  DTI (`USE_DTI=true`) with a note that JIT was removed.

Deliberately LEFT stale (per doc doctrine): `planning_documents/TODO.md` (banner:
"SUPERSEDED -- historical record only"), `docs/archive|audits|journal/*`, and the
`getJITHandshakePayload` frontend function name + its history-note references
(renaming the function is a wider refactor outside nee9's scope).

## Verification

Full backend suite green (982 passed / 2 skipped); the WS-protocol contract test
(82) still green after the table-heading rename; FE `schemaFormState` test (78)
green; `recompute_si_scenarios()` runs and produces an honest `jit`-drift-0 +
live `full`/`drip`. No `schema-editor/` app files touched.

## Scar tissue

Renaming a `###` heading in a wire-contract doc can silently break a contract test
that parses the doc by heading string (`test_websocket_protocol.py` looks up its
key tables that way). When editing a doc a test reads, grep the tests for the exact
string you are changing and update both together. Cross-ref bd polyglot-pdf-en2j
(the purge these clean up after).
