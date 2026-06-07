---
date: 2026-06-07
bead: polyglot-pdf-dx7
title: "Stop Gemini reading the raw field_id aloud"
tags: [bugfix, voice-ai, prompt]
---

## Trigger

`bd polyglot-pdf-dx7`. Live test (session `fss_mq4c81vs`): when asking for a
field, Gemini speaks the raw field_id -- e.g. it says "field_id
p1_line1_aliennumber" -- which is confusing for the user.

## Root cause

The frontend's `formatNextFieldHint` (`frontend/src/navigation.ts`) appends a
technical parenthetical to the SPOKEN hint:

    Next field to fill is #1: 'Alien Registration Number' (field_id: 'p1_line1_aliennumber', type: text)

That whole string flows to Gemini as the spoken hint (via the `confirm_field`
tool response's `next_field_hint`, and via the initiating / section-switch
message), and Gemini reads the parenthetical out loud. Two gaps let it through:

1. The field_id was in the spoken text at all.
2. The legacy `SYSTEM_INSTRUCTION` (the one actually in use) lacked the "Never
   read field IDs aloud" constraint that `JIT_SYSTEM_INSTRUCTION` already has.

The field_id is NOT needed in the spoken hint: Gemini gets every field_id from
the system instruction's FIELDS block (`ai_context` -> "ID: <field_id>"), which
is what it passes to `update_form_fields`. So stripping it from the spoken hint
does not affect tool-calling.

## Fix

- `backend/services/field_utils.py`: new `strip_field_id_from_hint()` -- removes
  the trailing `(field_id: '...', ...)` parenthetical (leaving the spoken name,
  including any parens the name itself contains, intact).
There are FOUR distinct spoken-hint paths (fresh-eyes + Copilot review of PR #112
found that the first cut covered only two). All four are now stripped:
- `backend/services/request_coordinator.py` (`handle_next_field_hint_response`) --
  the steady-state per-field hint returned in the `confirm_field` tool response.
- `backend/services/form_filling_service.py` (`send_initiating_message`) -- the
  language-change / section-switch greeting that formats the hint into
  `INITIATING_MESSAGE` directly.
- `backend/services/form_filling_service.py` (`send_manual_field_update`) -- when
  the user types a value manually, the next hint is appended to the message sent
  to Gemini (via AudioHandler). MISSED in the first cut.
- `backend/services/form_filling_service.py` (`build_form_context_message`) -- the
  SESSION-START path: the `initial_field_hint` from the handshake is interpolated
  into the system instruction's "ask for: {next_field_hint}" directive, which is
  what Gemini speaks in its very first greeting. MISSED in the first cut, and the
  most user-visible (it's the field_id you hear immediately on load).
- `backend/config.py`: add the "Never read field IDs aloud (use spoken names
  only)" + "natural phrasing, no IDs" constraints to the legacy
  `SYSTEM_INSTRUCTION` (belt-and-suspenders; matches the JIT template's wording).

`send_recovery_prompt` and `restart_gemini_session` take a `next_field_hint`
param but do NOT interpolate it into spoken text (recovery uses static
`RECOVERY_PROMPT_LEVEL_*`; restart rebuilds the SI via `build_form_context_message`
without threading the hint), so they needed no extra change.

**Regex (review):** the strip is END-ANCHORED (`\s*\(field_id:\s*'[^']*'.*\)\s*$`)
rather than stopping at the first `)`. An options list can contain `)` (e.g. an
option value "Other (specify)") or `'` (e.g. "O'Brien"); a first-`)` match would
half-strip and leave a dangling fragment Gemini might read. Anchoring to the final
`)` removes the whole trailing group while preserving the spoken name's own parens
(e.g. "(A-Number)") that come before the field_id group.

## Tests

`backend/tests/unit/test_strip_field_id_from_hint.py` (7): the exact frontend
hint shape; required/options suffixes; an option value containing `)` ("Other
(specify)") and one containing `'` ("O'Brien") -- the cases the first-`)` regex
would have half-stripped; a spoken name that itself contains parens (e.g.
"(A-Number)") is preserved while the field_id group is removed; no-op when absent;
None/empty pass through. Full suite: 217 passed.

## Scope note

This is issue 1 of two from the live test. Issue 2 (Gemini not responding / field
not filled) was a DEPLOY problem, not code: the live revision was still running
3.1 (`USE_PREMIUM_MODEL=true`) -- the 2.5 switch (bd polyglot-pdf-5oq) was merged
but the deployed build predated it / came from a stale checkout. A redeploy from
current `dev` (which has `USE_PREMIUM_MODEL=false` in config + deploy-demo.sh)
fixes it; no code change in this PR for issue 2.

## Doc freshness

No tier-2/3 doc describes the SPOKEN-hint content or the field-id-reading
behavior this change touches. The freshness checker flags several docs because
`config.py` / `form_filling_service.py` / `callback_handler.py` changed, but they
document unrelated concerns (compression, schema-forms, websocket-routing,
confirmation AUDIT logging, logging/cost, risk-rating, statelessness,
terminology) -- none are contradicted by stripping a field_id from a spoken hint
or adding a "don't read IDs aloud" instruction. `confirmation-and-audit.md`
mentions `field_id` only as the audit key (unchanged here). Left as pre-existing
drift from other PRs.

## Files touched

- `backend/services/field_utils.py` -- `strip_field_id_from_hint` helper
  (end-anchored regex).
- `backend/services/request_coordinator.py` -- strip the runtime confirm-field hint.
- `backend/services/form_filling_service.py` -- strip in `send_initiating_message`,
  `send_manual_field_update`, AND `build_form_context_message` (the session-start
  system-instruction path).
- `backend/config.py` -- "never read field IDs aloud" constraint in the legacy SI.
- `backend/tests/unit/test_strip_field_id_from_hint.py` -- new (7 tests).
