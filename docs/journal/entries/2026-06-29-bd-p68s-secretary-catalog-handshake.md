---
date: 2026-06-29
bead: polyglot-pdf-p68s
title: "Secretary: client supplies full schema at handshake + shown/applicability in form state"
sprint: 7
tags: [testing, conventions]
---

## Trigger

bead polyglot-pdf-p68s (the sprint-7 plan's child "jnjj.45d") -- the last open
dependency of the secretary feature build (jnjj.45). The secretary (a cheap text
model behind the `ask_secretary` tool) needs two inputs the stateless backend
cannot derive in DTI mode: (a) the WHOLE form's catalog, and (b) per-field
applicability (`shown`). The earlier children (.45a renderers, .45b
`TextAIGemini.ask`, .45c the tool + handler) all landed; the handler already
*consumed* a full schema and a `shown_map`, but nothing *delivered* them -- the
backend only had the current section's schema, and `form_state_response` carried
only `{value, confirmed}`. This bead wires the two client-owned inputs through.

## What shipped

Two parts, plus the end-to-end verification the criterion demanded.

(a) **Full-form catalog at handshake.** The browser now sends `full_schema`
(the whole form -- all parts/sections/fields) on every (re)connect, added to all
three handshake builders: `getHandshakePayload` and `getJITHandshakePayload`
(`schemaFormState.ts`) and the inline `startSection` handshake
(`webFormConnection.ts`). The backend parses it in `websocket_routes.py`
(`isinstance` dict guard), threads it through `_handle_fill_session` ->
`start_session`, and caches it as `FormFillingService._full_schema` -- kept
SEPARATE from the per-section `self._schema` (which drives the live-model SI) and
preserved across the internal section-switch restart (`start_session` only
overwrites when `full_schema is not None`; the internal
`_switch_to_section_locked` path does not thread it). `handle_ask_secretary` now
renders the secretary catalog from `self._full_schema or self._schema` -- the
WHOLE form, falling back to the section schema for an older client. Schema only,
no PII; rebuilt from the handshake on reconnect, so the stateless invariant holds.

(b) **`shown` on the form-state round-trip.** `handleGetFormStateRequest`
(`webFormConnection.ts`) adds `shown = shouldShowField(field, fieldValues,
fields)` to every `form_state_response` entry, in both the all-fields and the
requested-field branches, with the same `[]`-bracket fallbacks used for value
lookup. The backend `request_coordinator` is pass-through, and
`handle_ask_secretary` already built the `shown_map` from the entries' `shown`
key -- so no backend coordinator change was needed.

**Exit criteria:** both PASS. Criterion 2 (shown round-trips; a hidden field
reports `shown=false`) is covered by a new FE test file. Criterion 1 (backend
holds the full catalog + a real shown_map, verified end-to-end on the I-90 via
the voice-harness) was verified LIVE: the voice-harness gained `ask_secretary`
support (a TTS fixture asking a cross-field question, `runSecretaryQuery`, and
RUNBOOK step 6c), and a live run against real Gemini (Vertex) showed the model
call `ask_secretary` and the backend log `ask_secretary_complete` with
`field_count=1, shown_count=1, answer_len=61` -- a real shown_map from the client
plus a non-empty prose answer, no fail-open lines.

**Fresh-eyes:** two rounds (Sonnet). Round 1 found one gap -- criterion 1's live
E2E was unevidenced -- which drove building the secretary voice-harness path and
running it live (adopted), plus two secondary findings adopted: a JIT-handshake
`full_schema` coverage gap (added legacy + JIT assertions to
`schemaFormState.test.ts`) and a doc history-chain in `ws-protocol.md` (rewritten
to a single current-state stamp). Round 2 returned NO-GAPS with both criteria
PASS; its three non-criteria observations were all adopted (a dead `seedFields({})`
call removed, the journal-link target created -- this file, and a `start_session`
docstring corrected to say the client sends `full_schema` on every handshake
incl. manual section switches, only the INTERNAL restart omits it). No
out-of-scope beads filed.

**Out-of-scope fix folded in (defended):** `test_no_pii_logging.py`'s backend
file sweep walked `backend/.venv` (9005 third-party `site-packages` files,
failing on their `print()`s) when run from the main repo, which has the venv.
Added `.venv`/`venv`/`site-packages` to the sweep's skip list. Pre-existing bug
(fails identically on clean `dev`); folded in rather than filed separately
because it gates this PR's own test suite and is a reversible, no-product-impact
test-infra fix.

## Lessons

- **A "client supplies X" bead is two-sided, and the consumer may already be
  defensive.** The `.45c` handler was written to read `self._schema` and a
  `shown_map` it tolerated being empty; this bead only had to make those real.
  Reading the consumer first (rather than the bead title) showed the backend
  coordinator needed no change at all -- the FE was the whole of part (b).
- **The voice-harness only proves what it has a fixture + cycle for.** Its design
  (digit-fill / confirm) did not cover `ask_secretary`; "verify via the
  voice-harness" required net-new harness support (fixture + `runSecretaryQuery` +
  a backend-log assertion, since the secretary answer rides audio, not the
  webFormConnection message path the harness observes). Recorded in RUNBOOK 6c.
- **Local form-kits + the harness module are gitignored / untracked in a fresh
  worktree.** `frontend/public/form-kits/` (gitignored) had to be copied in for
  vite to serve the I-90 schema, and `harness.js` (under `tests/`) copied to
  `public/` to be fetch+eval'd. Neither is committed; noted here so the next live
  run does not rediscover it.

## Doc freshness

- `docs/standards/ws-protocol.md`: BUMPED. Documented the new `full_schema`
  handshake key (both modes) and the `shown` sub-field on `form_state_response`,
  added `full_schema` to the no-drift key list, and rewrote the `Last updated:`
  line to a single current-state stamp pointing here (was a history chain --
  fresh-eyes finding, current-state-only rule).
- All other STALE docs flagged by `check_doc_freshness.py` (voice-and-vad,
  validation-delegation, technical_guide, jit-schema, stateless-architecture,
  etc.) were already stale before this branch (their referenced file mtimes
  predate this work) and track files this branch did not change in a way that
  affects their prose -- reviewed and LEFT. `ws-protocol.md` is the canonical wire
  contract and the only doc this change's wire-format additions belong in.

## Files touched

- `frontend/src/schema-forms/state/schemaFormState.ts` -- `full_schema` added to
  both handshake builders.
- `frontend/src/webFormConnection.ts` -- `full_schema` on the `startSection`
  handshake; `shown` on every `form_state_response` entry.
- `backend/routes/websocket_routes.py` -- parse `full_schema`, thread through to
  `start_session`.
- `backend/services/form_filling_service.py` -- cache `_full_schema` (preserved
  across the internal restart); `handle_ask_secretary` prefers it.
- `backend/tests/unit/test_ask_secretary_handler.py` -- +2 tests (full-schema
  preference; cache survives a section-switch restart).
- `frontend/src/webFormConnection.secretary.test.ts` -- NEW (4 tests: handshake
  `full_schema`, hidden field `shown=false`, trigger-met `shown=true`, `shown` on
  a requested-field response).
- `frontend/src/schema-forms/state/schemaFormState.test.ts` -- +2 tests
  (`full_schema` on the legacy AND JIT/DTI builders).
- `backend/tests/test_no_pii_logging.py` -- sweep skips `.venv`/`venv`/`site-packages`.
- `tests/e2e/voice-harness/{gen_fixtures.py,harness.js,RUNBOOK.md}` -- secretary
  query fixture + `runSecretaryQuery` + RUNBOOK step 6c.
- `frontend/public/test-fixtures/secretary_query_alien.wav` -- NEW committed fixture.
- `docs/standards/ws-protocol.md` -- documented the two new wire keys.
