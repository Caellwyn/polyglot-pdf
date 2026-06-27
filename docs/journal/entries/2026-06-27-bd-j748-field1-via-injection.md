---
date: 2026-06-27
bead: polyglot-pdf-j748
title: "Deliver field 1 guidance via the initiating injection (not the SI)"
sprint: 7
tags: [refactor, conventions, testing]
---

## Trigger

Child B of the fully-static DTI system-instruction epic (polyglot-pdf-13w7; plan
`docs/sprint_7_static-si_plan.md`). Child A (polyglot-pdf-1ac3, merged in PR #252)
made the DTI system instruction (SI) fully static -- it no longer carries field 1's
guidance. That left a real gap, which Codex flagged on PR #252: in DTI mode the
live Gemini model had NO way to learn field 1's exact field_id, because the static
SI holds no field data AND `send_initiating_message` strips the field_id from the
spoken hint. Without field 1's id the model cannot make the first
`update_form_fields` call. Child B closes that gap by delivering field 1's full
guidance through the INITIATING MESSAGE -- the same injection channel that already
delivers fields 2..N via the `confirm_field` response. This PR also bundles the
small follow-up bead polyglot-pdf-39ik (fix the now-stale `render_field_guidance`
docstring), whose surface (`ai_context.py`) this PR already edits.

## What shipped

- **config.py**: `INITIATING_MESSAGE` + `RESUME_INITIATING_MESSAGE` gain a trailing
  `{current_field_guidance}` placeholder. The caller passes `""` in non-DTI mode,
  so legacy/JIT output is byte-for-byte unchanged.
- **form_filling_service.py**: `send_initiating_message` now renders field 1's
  guidance from `self._schema["fields"][0]` (the client-selected first unfilled
  field, same source the old DTI SI branch used) via `render_field_guidance` -- the
  SAME renderer that delivers fields 2..N -- and threads it into both templates.
  DTI-gated (`getattr(self._settings, "USE_DTI", False)`). The field_id stays IN
  the guidance block (context the model copies verbatim) but is still stripped from
  the SPOKEN hint (bd dx7), so Gemini does not read the id aloud. Logging still
  records only `message_length` (no-PII guard, bd uov.15).
- **websocket_routes.py**: added the missing DTI session-start trigger -- fire the
  initiating message right after `start_session` so field 1 reaches Gemini at
  session/section start (the legacy/JIT path is kicked off by the SI alone, so it
  is DTI-gated to avoid a double-greeting). Resume is honored via
  `service._is_resume_session`.
- **ai_context.py**: the static DTI SI branch no longer `.format()`s the (now
  absent) placeholders -- it returns the constant directly, removing the dead
  `current_field_guidance` compute that PR #252 left behind. Also rewrote the
  `render_field_guidance` docstring to describe the injection path, not the SI
  (this IS bead polyglot-pdf-39ik, folded in).
- **Tests** (test_dti.py, 5 new): field-1 id+guidance present in the DTI initiating
  message and identical to `render_field_guidance` output (criterion 1); no
  guidance block in non-DTI mode; the RESUME template still carries field-1
  guidance (reconnect edge); empty-schema injects no `No fields available`
  sentinel and does not crash; logging records only `message_length`. Full backend
  suite: 441 passed / 2 skipped (from the worktree).

**A real bug the suite caught.** My first session-start trigger referenced
`get_settings()`, but a function-local `from backend.config import get_settings`
later in the same function made that name local for the whole function scope --
an `UnboundLocalError` that would have crashed every DTI session start.
`test_websocket_schema_initializes_session` failed and surfaced it; fixed by
relying on the module-level `get_settings`/`settings` and renaming the watchdog's
local to `local_settings`. Recorded as a durable lesson via `bd remember`
(`websocket-routes-local-get-settings-shadows-module`).

**Exit-criteria scorecard (Assess, Step 5.5.a):**
- j748 #1 (field 1's exact field_id + guidance is in the initiating injection, not
  the SI) -- PASS: `send_initiating_message` renders it; the SI is static.
  `test_initiating_message_carries_field1_guidance_in_dti`.
- j748 #2 (hallucination drops over the measure runs) -- PASS as "mechanism in
  place." Criterion 2 is measured by the later bead polyglot-pdf-h1bn (>=10 live
  runs); j748 puts the delivery mechanism in place and unit-verifies it.
- 39ik #1 (docstring no longer references `{current_field_guidance}`/the SI; it
  describes the injection path) -- PASS: docstring rewritten (ai_context.py).

Fresh-eyes adversarial assess (Sonnet, arm B picker -> sonnet): NO-GAPS on both
bead rubrics in round 1. It verified the get_settings shadowing fix is real and
complete, non-DTI byte-identical output, no double-greeting, the strip-regex test
input is realistic, and the empty-schema guard. Two findings beyond the rubric:
- Finding 1 (test quality, ADOPTED): my `test_initiating_message_logs_only_length`
  was vacuous -- it used pytest `caplog`, but `_log` is a structlog logger not
  routed through stdlib in tests, so `caplog.records` is empty and the assertions
  passed for free. First rewrote to `structlog.testing.capture_logs()`, but that
  FAILED in the FULL suite (passed isolated) -- the module-level lazy `_log` is
  already realized against the suite's structlog config, so a global-config swap
  does not reliably intercept it (ordering-dependent flake). Final approach:
  monkeypatch the module's `_log` with a fake whose `.info()` records the call
  kwargs -- deterministic and ordering-independent. Mutation-verified twice
  (injected `leak=field_id` -> test FAILED; reverted -> passed). Since the rubric
  was already NO-GAPS and this is a self-contained test-only fix I mutation-verified
  directly, I did not re-spawn fresh-eyes for it.
- Finding 2 (out-of-scope, FILED then CLOSED as duplicate): restart_gemini_session
  does not fire the initiating injection in DTI mode (Level-3 farewell + restart
  loses field 1). Fresh-eyes filed polyglot-pdf-88m6; on review it is an exact
  duplicate of epic child h1bn's edge-case (a) ("restart_gemini_session ... must
  fire an initiating injection after set_callbacks"), so I closed 88m6 pointing at
  h1bn (which owns the fix). Out of j748's session-start-only scope.
Adopt: 1 (PII test hardening). Reject: 0. Defer: 0 net new (88m6 closed as dup of h1bn).

## Lessons

A function-local `import`/rebind of a name that also exists at module scope makes
that name local for the ENTIRE function body, so any earlier reference raises
`UnboundLocalError`. In `websocket_routes.py::_handle_fill_session` a watchdog-local
`get_settings` re-import shadowed the module-level one and crashed the new
session-start gate. Use module-scope names inside that function; no local rebind.
(bd remember `websocket-routes-local-get-settings-shadows-module`.)

## Doc freshness

- `docs/components/websocket-routing.md` -- BUMPED. My change adds a new behavior
  (the DTI session-start initiating message), so the handshake section now
  documents it as step 6 and the stamp points here. This is the doc that genuinely
  tracks the file + behavior I changed.
- `docs/standards/voice-and-vad.md` mentions the initiating message for
  `change_spoken_language`; my change does not alter that path's contract (it still
  fires; in DTI it now also carries guidance), so its prose stays true. Left.
- `docs/standards/si-reduction.md` (the SI-shape contract) documents only the
  Legacy/JIT templates and never the DTI initiating-message channel -- already
  stale w.r.t. DTI, and my change does not falsify its Legacy/JIT prose. Refreshing
  it to cover the now-static DTI SI + injection channels is the static-SI epic's to
  own. Left.
- The other config.py-tracking flagged docs (ai-models, logging-and-cost,
  tool-call-flow, etc.) do not describe the initiating-message field-1 channel and
  are stale from other recent commits to files this branch did not touch. Left.

## Beads housekeeping

No orphans. Three stale in_progress beads (hrn, jf6w, ue5s) are pre-existing,
unrelated to this branch, and owned by the maintainer / long-running epics -- not
this bead's to transition. Noted and left.

## Files touched

- `backend/config.py` -- `{current_field_guidance}` suffix on both initiating templates.
- `backend/services/form_filling_service.py` -- render + thread field-1 guidance (DTI-gated) in `send_initiating_message`.
- `backend/routes/websocket_routes.py` -- DTI session-start initiating-message trigger; fix `get_settings`/`settings` shadowing.
- `backend/services/ai_context.py` -- static DTI SI returned directly (drop dead `.format`); fix `render_field_guidance` docstring (bd 39ik).
- `backend/tests/unit/test_dti.py` -- 5 new DTI initiating-message tests.
- `docs/components/websocket-routing.md` -- document the DTI session-start initiating message.
