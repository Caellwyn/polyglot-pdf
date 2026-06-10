---
date: 2026-06-10
bead: polyglot-pdf-aun
title: "WS-D: section-switch durability (frontend re-entrancy guard + error surfacing)"
tags: [hotfix, testing]
---

## Trigger

WS-D of the voice round-trip hardening epic (`polyglot-pdf-wpw`), re-scoped
frontend-only (the backend switch serialization moved into `0c1`). The FE used
`isSectionSwitching` as BOTH the auto-reconnect suppressor AND an implicit switch
guard. That conflation had two failure modes the demo can't have: a switch that
failed mid-flight (a reconnect drop, a server error, or a hang) left the UI stuck
on `switching_section` forever -- `handleClose` returns early on
`isSectionSwitching` and `handleServerError` never touched the status -- and a
second overlapping switch was not prevented.

## What shipped

`frontend/src/webFormConnection.ts`:
- **`switchInFlight`** -- a real re-entrancy guard, distinct from
  `isSectionSwitching` (which clears the instant the new socket opens). Set across
  the whole switch, released by `completeSectionSwitch`/`failSectionSwitch`. Both
  `startSection` (reconnect path) and `switchToSection` (in-session path) reject a
  second switch while one is in flight -- the FE no longer even sends the second
  `manual_section_switch` the backend (post-`0c1`) would reject.
- **A ~15s watchdog** (`armSectionSwitchWatchdog`) surfaces `error` if a switch
  neither confirms (`section_switched`) nor errors -- no stuck `switching_section`.
- **`failSectionSwitch`** settles status to `error` + fires `onError` on every
  failure path: a failed reconnect/handshake (`startSection` catch), a server
  `error` mid-switch (`handleServerError` -- including the backend's
  `section_switch_failed` rejection of a concurrent switch), an unexpected
  mid-switch socket close (`handleClose`), or the watchdog.
- **`completeSectionSwitch`** releases the guard + disarms the watchdog when
  `section_switched` arrives, before settling to `connected`.

Tests (`webFormConnection.switchdurability.test.ts`, vitest + fake timers):
re-entrancy reject; server-error -> `error` recovery; watchdog -> `error`;
`section_switched` -> `connected` (guard + watchdog cleared, no late watchdog
fire); a non-switch server error leaves status untouched. 192 frontend tests
pass; no new `tsc` errors (the 4 `webFormConnection` errors are pre-existing on
`dev`).

Fresh-eyes triage: recorded in the merge ping (this entry predates the review).

## Lessons

- **One flag doing two jobs is a state-machine bug waiting to happen.**
  `isSectionSwitching` had to clear early (to let the new socket's handshake
  proceed) AND stay set late (to gate re-entry and catch a failed switch) -- two
  irreconcilable lifetimes. Splitting it into a short-lived reconnect suppressor
  and a switch-long `switchInFlight` guard resolved the conflict.
- **A failure surface needs an explicit terminal state.** The old code had no path
  from `switching_section` to `error`; every failure route now funnels through one
  `failSectionSwitch` that sets the terminal status + fires `onError`.

## Doc freshness

Updated `docs/components/websocket-routing.md` -- added a "Client-side switch
durability" paragraph to its Section-switch flow (the natural home for the new
failure behavior) and bumped its stamp. The other two flags
(`stateless-architecture.md`, `voice-and-vad.md`) `Track:` `webFormConnection.ts`
by glob but this change touches neither statelessness nor VAD -- reviewed and left.

## Files touched

- `frontend/src/webFormConnection.ts` -- switchInFlight guard, watchdog,
  failSectionSwitch/completeSectionSwitch, wired into startSection /
  switchToSection / handleSectionSwitched / handleServerError / handleClose.
- `frontend/src/webFormConnection.switchdurability.test.ts` -- new vitest suite.
- `docs/components/websocket-routing.md` -- client-side durability note + stamp.
