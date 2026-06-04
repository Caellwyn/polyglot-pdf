---
date: 2026-06-04
bead: polyglot-pdf-tb7
title: "Token-log section context fix + part->section wire-format rename"
tags: [bug, logging, conventions, wire-format]
---

## Trigger

Bundle of two related beads on the section-state terminology + token-log surface:

- `bd polyglot-pdf-tb7` (bug): `set_session_context` was always called with
  `current_section_id=None`, so every `token_usage.jsonl` event logged a null
  section -- the per-section cost breakdown the field was meant to provide was
  never populated. A `# Will be updated on section switch` comment promised an
  update no code path performed.
- `bd polyglot-pdf-zun` (chore): rename the section-state `part` wire-format
  holdouts to section-canonical names, sequenced against consumers. Split out
  from `gfb.4` (which did the safe internal renames).

The two beads explicitly said to land together so the token-log key and its
value land correctly.

## What shipped

**tb7 -- thread the real section id into the token-log context:**

- `form_filling_service.start_session` gained a `current_section_id` param,
  forwarded into `set_session_context` (replacing the hardcoded `None`).
- The WS route (`websocket_routes.py`) threads the handshake `section_id`
  through `_handle_fill_session` -> `start_session` on initial connect.
- `switch_to_section` passes `section_metadata["section_id"]` on each switch.
- Frontend parity: the AI-driven `section_info_response` metadata
  (`webFormConnection.ts`) now includes `section_id`, matching the manual-switch
  path that already had it. Without this, AI-initiated switches would still log
  a null section.

**zun -- rename the `part` wire-format holdouts (the surfaces that cross a real
producer/consumer boundary):**

- Token-log payload: `token_file_logger.py` param + key `part_id` -> `section_id`;
  `live_ai_gemini.py` call site `part_id=` -> `section_id=`. The local-dev
  consumer `token-monitor/dashboard.html` now reads `event.section_id` with a
  `?? event.part_id` fallback (the JSONL accumulates old + new lines) and the
  table header is now "Section".
- WS-handshake manifest (frontend-internal): `manifestUtils.ts`
  `current_part`/`previous_parts`/`part_id`/`part_label` ->
  `current_section`/`previous_sections`/`section_id`/`section_label`
  (+ `PartManifest`->`SectionManifest`, `generatePartManifest`->
  `generateSectionManifest`, "CURRENT PART"->"CURRENT SECTION" context text, and
  the "Part ... not found" error -> "Section").

**Scope correction (verified against code, not the bead text):** zun's
description claimed the handshake `part_id`/`part_label` rename "requires changing
BOTH ends in lockstep (frontend producer + backend consumer)." That is wrong: the
Python backend (`websocket_routes.py`) consumes ONLY `manifest.parts` (the section
navigation list, already section-canonical `{id, order, label}`), NOT the
`current_part`/`part_id` keys. So the handshake rename is frontend-internal. The
`parts` key keeps its name because that IS the backend wire contract.

**Deliberately deferred (out of zun's two named surfaces):**
`backend/services/manifest_service.py` `generate_part_manifest` /
`format_manifest_for_context` -- a separate backend-internal path feeding the
Gemini system instruction ("CURRENT PART: ..."). Renaming it changes prompt
wording (behavior-adjacent) and it is on neither wire format. Left as-is and
documented in `docs/standards/terminology.md`.

## Tests

- New `backend/tests/unit/test_token_file_logger.py`: asserts the payload carries
  `section_id` (and no legacy `part_id`), that a real section id is logged, and
  that it defaults to null when omitted.
- `test_section_switching.py`: new test asserts the section id threads into
  `set_session_context` on `switch_to_section`.
- `manifestUtils.test.ts`: rewritten to the section API. It had been stale --
  passing `FormPart`s where `FormSection`s are expected and using
  `currentPartId`/`completedParts` that don't match `SchemaFormState`; the rewrite
  exercises the renamed functions correctly with proper section fixtures.
- Backend unit: 103 passed (full closeout run: 178 passed, 2 skipped).
- Frontend manifest: 20 passed. Frontend `tsc` errors 48 -> 24 (the test rewrite
  fixed 24 pre-existing errors; zero introduced; the files I touched are
  `tsc`-clean).

## Doc-freshness note (reviewed, no content change needed)

closeout_prep flagged ~13 docs stale purely on mtime (I touched
`live_ai_gemini.py`, `websocket_routes.py`, `token_file_logger.py`,
`form_filling_service.py`, `webFormConnection.ts`). Reviewed each against this
diff: none describe the old `part_id` token-log key, and several
(`voice-ai.md` documents `set_session_context(..., current_section_id)`,
`websocket-routing.md`/`stateless-architecture.md` already use `section_id`) are
made *more* accurate by this change, not less. No tier-1/2 doc content is now
wrong. Only `terminology.md` -- which I substantively edited (updated the holdout
list + corrected the lockstep claim) -- had its `Last updated:` bumped to
2026-06-04.

## Pre-existing slip noted (not mine to transition)

closeout_prep flagged `polyglot-pdf-hrn` (P1) in_progress > 1d. That is a separate
harness-tuning epic, untouched by this PR; left as-is rather than transitioning
another work-stream's in-progress bead.
