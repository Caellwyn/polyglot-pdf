---
date: 2026-07-06
bead: polyglot-pdf-x8rt
title: "Production continuous-session mode: whole form as one DTI+compression session (replaces section resets)"
tags: [performance, refactor]
---

## Trigger

ctu8 proved a continuous DTI session with a ~3500 compression window is cheaper
AND more coherent than the section-reset mechanism, and the maintainer called the
cutover. But the cutover turned out NOT to be a flag flip: production had no
continuous-session mode. Section switching is driven by the FRONTEND advancing
through `schema.sections` and the MODEL calling `switch_section` -- neither gated
by `USE_DTI` or the compression flags. The ctu8 experiment faked "continuous"
with a harness-only flag that fed the whole form as one synthetic section.
Flipping the flags alone would have shipped DTI-in-sections (the coexistence case
we explicitly did not want), not the continuous replacement.

## What shipped

A real `CONTINUOUS_SESSION` feature (default off; section-reset path untouched
when off) across backend + frontend + the demo deploy:

- **Backend** (`config.py`, `websocket_routes.py`, `form_filling_service.py`):
  the flag; `session_ready` carries `continuous_session_enabled`; the
  `switch_section` tool is dropped from the declarations when continuous (a stray
  call can't reset the session we keep open); the "Section N of M" metadata is
  suppressed in the DTI initiating message (which also drops the derived
  next-section confirmation-policy line). No SI-template edits -- the DTI SI
  already carries no section guidance.
- **Frontend** (`schemaFormState.ts`, `manifestUtils.ts`, `navigation.ts`,
  `webFormConnection.ts`): `continuousSessionEnabled` state (init + migration +
  setter, mirroring `jitModeEnabled`); `buildContinuousManifest` builds one
  synthetic `continuous` section carrying EVERY field in schema order;
  `getJITHandshakePayload` uses it with `total_sections=1`; both section-advance
  paths are suppressed (`proceedSectionSwitch` early-returns,
  `handlePrepareSectionSwitchRequest` rejects).
- **Deploy** (`deploy-demo.sh`): the demo backend env now sets
  `USE_DTI+CONTINUOUS_SESSION+CONTEXT_COMPRESSION_ENABLED+TRIGGER_MARGIN_TOKENS=1500`.
  The margin=1500 lands the window at the ctu8-VALIDATED 3500 (5000 Vertex-clamped
  trigger - 1500); the default margin (600) would have derived the UNTESTED 4400.
  Reversible by dropping the four vars.
- **Tests**: `buildContinuousManifest` (FE, 3) + `switch_section`-drop (BE, 1).

Fresh-eyes assess: (recorded at closeout).

## Lessons

- **`computeNextField` was section-scoped and would have stalled the fill at
  section 1.** It filtered to the current section's fields; in continuous mode
  there is no section advance to carry the fill onward, so it would have returned
  null at the first section's last field and stopped. Fixed to span the whole form
  when `continuousSessionEnabled`. The general trap: a "run it all as one" mode has
  to audit every place that was implicitly section-scoped, not just the obvious
  handshake + advance seams.
- **The flag flip and the window value are two separate things.** Enabling
  continuous mode does NOT set the window to the validated 3500 -- the per-form
  derivation + Vertex clamp lands it at 4400 unless `TRIGGER_MARGIN_TOKENS` is set
  to 1500. Shipping the flags without the margin would have run an untested window.
- **"Cut over" hid a multi-surface feature.** The honest scope was frontend
  handshake + navigation + both advance paths + backend flag/tool/metadata, not a
  config toggle. Surfacing that as an escalation (rather than silently expanding)
  let the maintainer choose to build it properly.

## Doc freshness

`docs/standards/ws-protocol.md` updated: the `session_ready` table gains the
`continuous_session_enabled` key (the contract test
`test_session_ready_keys_match_doc` pins this and caught the omission), stamp
bumped. No other tier-1/2 doc tracks the changed files in a way this branch
altered.

## Files touched

Backend: `config.py`, `routes/websocket_routes.py`,
`services/form_filling_service.py`. Frontend:
`schema-forms/state/schemaFormState.ts`, `schema-forms/utils/manifestUtils.ts`,
`navigation.ts`, `webFormConnection.ts`. Deploy: `deploy-demo.sh`. Docs:
`standards/ws-protocol.md` + this entry. Tests: `backend/tests/unit/test_dti.py`,
`frontend/src/schema-forms/utils/manifestUtils.test.ts`.
