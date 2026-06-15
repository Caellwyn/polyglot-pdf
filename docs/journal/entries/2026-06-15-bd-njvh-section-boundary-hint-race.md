---
date: 2026-06-15
beads: [polyglot-pdf-njvh]
pr: TBD
tags: [performance, testing]
---

# njvh: skip the racing next-field-hint at a section boundary

## Trigger

A deferred PR #141 fresh-eyes finding (bd wpw.2), now in the now-open reconnection
area (the reconnection session retired; this is the "preventing unintentional
failures" carve-out, not the active SI-diet / intentional-reset work). On the LAST
field of a section, `_handle_confirm_field_tool` fired `request_next_field_hint()`
right as the FE tore down the socket for `switchToSection` -- the hint request
raced the teardown, the coordinator returned `HINT_REQUEST_TIMEOUT`, and Gemini got
`next_field_hint:null` + a spurious "do NOT assume the form is complete" prompt at
the exact moment the section was correctly auto-advancing.

## Measurement first (the bead's scar: don't assume the cause)

The bead mandated measuring before changing. Findings:

- **The timeout half is empirically confirmed.** The existing Gemini-I/O dev-log
  (`backend/logs/gemini_2026-06-15.jsonl`) contained a real captured instance: a
  `confirm_field` response with `success:true, field_confirmed` BUT
  `next_field_hint:null` + the "Could not determine the next field right now -- do
  NOT assume the form is complete" message. Of 17 confirm responses, 1 hit the
  timeout, 5 were legitimate "All fields confirmed". So `request_next_field_hint`
  demonstrably DOES time out after a successful confirm.
- **The dev-log CANNOT isolate the section-boundary correlation.** It records only
  Gemini adapter I/O, not the FE-driven section switches (`switchToSection` is a
  client-side teardown + WS control-channel message, never Gemini I/O). The logged
  sessions were also mostly single-field / few-field test forms, not multi-section
  I-90 runs. So the dev-log proves the timeout half but not "at a boundary".
- **The code paths prove the race structurally** (read both sides):
  `_handle_confirm_field_tool` (callback_handler.py) unconditionally requests the
  hint after a recorded confirm; `handleConfirmFieldRequest` (webFormConnection.ts)
  acks the confirm then, on section-complete, calls `onStopCapture()` +
  `switchToSection()` which tears down the socket.

So the fix also CLOSES the observability gap (see below).

## What shipped

The FE now computes section-completeness BEFORE acking the confirm and sets
`section_complete:true` in `confirm_field_response` -- but **only when the current
section is done AND a NEXT section exists** (exactly the `switchToSection` branch).
The flag threads FE -> `websocket_routes` -> `FormFillingService` ->
`RequestCoordinator` (into the resolved ack dict) -> `_handle_confirm_field_tool`,
which then SKIPS `request_next_field_hint`, returns a clean "section advancing"
message (no scary timeout text), and logs `confirm_section_boundary_skip_hint` --
the section-boundary signal the Gemini-I/O dev-log lacked.

**The form-complete edge (caught by my own unit test before it shipped):** an early
version set `section_complete = !nextField`, which was true even on the LAST
section's last field -- where there is NO next section, the FE fires
`onFormComplete` (no `switchToSection`, no teardown), and the backend SHOULD request
the hint to get the genuine "All fields confirmed". Gating on a next section
EXISTING fixes that: `section_complete == (section done) AND (next section exists)`.

## Pre-PR assess + verification

Rubric (acceptance: a section boundary does NOT fire the spurious timeout/prompt;
mid-section + form-complete behavior unchanged; verified): the deterministic clauses
PASS; the "verified live on demo" clause is left for a maintainer eyeball (see
below).

- **6 new unit tests:** backend -- boundary skips the hint / mid-section still
  requests it / a missing `section_complete` key is back-compat; coordinator --
  `section_complete` plumbs through the resolved ack; FE -- the boundary sets the
  flag / a form-complete confirm does NOT. Plus 3 coordinator ack-shape assertions
  updated for the new key. Backend 353 pass; frontend 400 pass; tsc clean.
- **Live drive limitation (honest):** the bead's "verified live on the demo" clause
  was NOT met by an automated capture. I brought up the voice-harness stack and
  seeded the first 8 fields of I-90 section 1 (leaving only the last field via the
  `seedFieldConfirmed` dev hook, bd 8k8), but the audio injection -- driven by hand
  through Chrome MCP one-shot `javascript_tool` calls rather than the sustained
  811-line `harness.js` -- stalled twice mid-stream (the documented "do NOT
  improvise the audio injection" trap). The deterministic unit tests + the new
  observability log are the stronger correctness guarantee here; the live clause is
  a maintainer eyeball: on the next real demo session, a section-crossing confirm
  should emit `confirm_section_boundary_skip_hint` in the dev-log and NO "do NOT
  assume complete" message at the boundary.

Fresh-eyes (Sonnet, 1 round -> NO-GAPS): all 3 rubric criteria PASS; traced the full
FE->WS-route->service->coordinator->confirm-handler plumb chain (key name consistent
at every hop), confirmed the form-complete gate, the back-compat default, and the
confirm-ack-timeout early return. The `section_complete` sub-field vs. the SI-epic's
planned top-level event was confirmed to be documentation-only (no code collision).
Three findings, all addressed (none rubric gaps): (1) a stale `request_confirm_field`
docstring still listing the old 2-key return shape -> updated to document
`section_complete`; (2) the new FE boundary test's auto-`switchToSection` armed a
real ~15s watchdog `setTimeout` that could leak into a later test -> added an
`afterEach` that `disconnect()`s the connection (runs `clearSectionSwitchWatchdog`);
(3) the boundary ack assertion used `>= 1` -> tightened to exactly `toHaveLength(1)`
so a double-fire would fail. No out-of-scope beads filed.

## Lessons

A diagnostic log is part of the fix when the existing telemetry structurally can't
see the failure. Here the Gemini-I/O dev-log can never show the section-boundary
correlation (section switches are FE-driven, off the Gemini channel), so the fix
ships its own boundary signal (`confirm_section_boundary_skip_hint`) -- the race is
now observable for anyone, not re-investigated each time.

Also: "section complete" and "form complete" are different events at the same
trigger (the last field of a section vs. the last field of the LAST section). A flag
named for one will quietly mean the other unless gated on "a next section exists" --
a unit test on the single-section/form-complete case caught exactly this.

Generalizable -- noted in `docs/standards/*` if a home exists for it.

## Doc freshness

Bumped the 3 docs that genuinely describe what changed:
- `ws-protocol.md` -- documented the new optional `section_complete` sub-field on
  `confirm_field_response` in the message table, with an explicit note that it is a
  sub-field of the confirm reply, NOT the SI-reduction epic's planned top-level
  `section_complete` EVENT (same name, different thing -- flagged to avoid collision
  with that active work).
- `tool-call-flow.md` -- documented the section-boundary short-circuit in the
  confirm_field round-trip's "recorded" branch.
- `websocket-routing.md` -- noted the WS route reads + threads the flag (no dispatch
  structure change).

Left 6 docs flagged-but-stale: they track files this branch touched but describe
behavior this PR did NOT change -- `confirmation-and-audit.md` +
`hipaa-pii-policy.md` (callback_handler: my change is in the next-field-HINT path,
not the confirmation-audit logging; the new `confirm_section_boundary_skip_hint`
log is PII-free -- `field_id` + `session_id` only, both always-safe-to-log),
`context-compression.md` + `stateless-architecture.md` (form_filling_service: I only
added a param passthrough), and `auth.md` + `risk-rating.md` (websocket_routes
broadly: no auth/risk change). Per the doc-freshness rule, a doc stale on a file
this branch didn't behaviorally change is not this PR's to bump.

## Files touched

- `backend/services/callback_handler.py` -- section-boundary skip + the
  `confirm_section_boundary_skip_hint` log
- `backend/services/request_coordinator.py` -- thread `section_complete` into the
  resolved confirm ack
- `backend/services/form_filling_service.py` + `backend/routes/websocket_routes.py`
  -- plumb `section_complete` through
- `frontend/src/webFormConnection.ts` -- compute + send `section_complete` (gated on
  a next section existing)
- `backend/tests/unit/test_confirm_field_tool.py`,
  `backend/tests/test_request_coordinator.py`,
  `frontend/src/webFormConnection.confirmloop.test.ts` -- 6 new tests + 3 updated
  ack-shape assertions
