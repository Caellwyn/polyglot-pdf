---
date: 2026-07-13
bead: polyglot-pdf-kxkw
title: "W2: client-side stride window builder + validate_windows emit (page-agnostic)"
sprint: 12
tags: [refactor, testing]
---

## Trigger

Sprint-12 epic 09da (decoupled async validator), child W2 -- the CLIENT half of
the validator (W1 shipped the async backend). The revised plan (report-cadence
revision, bd c3uo) made validation PAGE-AGNOSTIC: run the flash-lite windows on a
field-count stride, not on page-boundary crossings, so a `source:"web"` / pageless
form (which carries no `pdf_position.page`) validates identically to a paginated
one. W2 builds the overlapping windows client-side and emits them.

## What shipped

As fields settle, the client sends overlapping windows (size 20, stride 10 over
`state.schema.fields` order) of settled field values to the backend validator as
ONE `validate_windows` message, tracking a persisted `validatedWindowIndices:
Set<number>` so each window is validated exactly once (across reloads too).

- `schemaFormState.ts`: new `validatedWindowIndices` Set on `SchemaFormState`
  (interface + init + save/load serialization, mirroring `loadedFieldIds`; empty
  default for pre-W2 sessions, no migration key). New PURE `computeReadyWindows()`
  helper returning the eligible-and-unsent windows.
- `webFormConnection.ts`: `VALIDATOR_WINDOW_SIZE/STRIDE` (20/10);
  `maybeEmitValidateWindows()` renders each ready window through the existing
  `buildValidatorFields` (contract-2 `{field_id,name,value,steered}`) and sends one
  `validate_windows`, immutably persisting the sent indices. Wired on the same 4
  state-change seams as `maybeEmitFormComplete` (confirm, skip, manual edit,
  reconnect).
- Bundled bd polyglot-pdf-he5z: the W1 backend `validate_windows` comment (and the
  ws-protocol.md / websocket-routing.md rows) still said "page-end / page-boundary
  trigger"; updated to "stride / settled" to match the shipped behavior. Removed
  `validate_windows` from the contract test's no-FE-sender exception set (W2 wired
  the emitter, so the test now enforces that it HAS a live sender).

**The eligibility rule -- redesigned after fresh-eyes (the key decision).** My
first cut fired a window once the fill's high-water CONFIRMED index PASSED the
window's end. Fresh-eyes (Sonnet) proved this STARVES fields: an out-of-order voice
fill (confirm f0..f19 but skip f5) or a trailing unanswered OPTIONAL field inside a
window's range would fire + permanently retire the window while that field was
still open -- its later confirmation never validated. Redesigned to: **a window is
eligible only when EVERY field it covers is SETTLED** (confirmed OR skipped OR
hidden-by-conditional / not-applicable). A still-open field inside the range keeps
the window pending, so nothing is starved; the tail window fires naturally at form
end with no separate `isFormComplete` release. This is more correct AND simpler
(dropped the `isFormComplete` dependency). Regression tests pin both the
out-of-order-f5 and skipped-field cases.

**Other fresh-eyes fixes (all adopted):** a CI-gating `tsc` error (test imported
`FormSchema` from `./schemaFormState`, which only type-imports it -> import from
`../types/schema`); the in-place `Set.add` mutation replaced with the codebase's
immutable spread-replace pattern; a `stride > size` coverage-gap guard (clamp the
enumeration step to `size` so windows always tile contiguously).

## Lessons

The natural "validate a region once the fill has moved past it" heuristic (a
high-water index) is WRONG for a non-linear fill: voice fills jump and optional
fields trail, so "past it" does not mean "done with it." The correct predicate is
"every field in the region is settled," where settled must include skipped and
not-applicable, not just confirmed -- else a legitimately-skipped optional field
blocks its window forever. Generalizes to any "this chunk is done" gate over a
form whose fields are not answered strictly in order.

## Doc freshness

- **Bumped** `docs/standards/ws-protocol.md` + `docs/components/websocket-routing.md`
  (the `validate_windows` rows: stride/settled trigger, page-agnostic, live FE
  sender) -- the he5z fix.
- **Reviewed and left** the other prep-flagged stale docs (auth, config-deployment,
  context-compression, jit-schema, pdf-filling, si-reduction, stateless-architecture,
  terminology, validation-delegation, voice-and-vad, technical_guide): transitively
  flagged by `config.py`/`websocket_routes.py`/`form_filling_service.py` mtimes, but
  W2 does not invalidate their current-state prose.

## Files touched

- `frontend/src/schema-forms/state/schemaFormState.ts` -- `validatedWindowIndices`
  Set (interface/init/save/load) + `computeReadyWindows` (all-settled eligibility,
  stride-clamp guard).
- `frontend/src/webFormConnection.ts` -- window-size/stride constants +
  `maybeEmitValidateWindows` (immutable state replace) wired at the 4 seams.
- `frontend/src/schema-forms/state/schemaFormState.validatorwindows.test.ts` (new)
  -- eligibility math incl. the starvation + skipped regressions, persistence.
- `frontend/src/webFormConnection.validatewindows.test.ts` (new) -- emit-on-settled,
  no double-send, overlapping emission, web==pdf.
- `backend/routes/websocket_routes.py` -- validate_windows comment (he5z).
- `backend/tests/contract/test_websocket_protocol.py` -- removed the no-FE-sender
  exception for `validate_windows`.
- `docs/standards/ws-protocol.md`, `docs/components/websocket-routing.md` -- bumped.
