# JIT schema loading -- infra audit (A1)

**Tracks:** backend/services/manifest_service.py backend/services/ai_context.py backend/routes/websocket_routes.py backend/services/form_filling_service.py frontend/src/schema-forms/utils/manifestUtils.ts frontend/src/schema-forms/state/schemaFormState.ts

*Last updated: 2026-06-14. Created as the A1 audit of the existing JIT (`USE_JIT_SCHEMA`) infra for the SI-reduction epic (bd polyglot-pdf-jnjj.8). See [../journal/entries/2026-06-14-bd-jnjj.8-jit-infra-audit.md](../journal/entries/2026-06-14-bd-jnjj.8-jit-infra-audit.md) for closeout details. The frozen target shape is [../standards/si-reduction.md](../standards/si-reduction.md).*

The JIT path (`USE_JIT_SCHEMA=true`, default OFF) was built by weaker models. This
is the A1 audit: a catalog of every correctness gap in that path, each tagged
**fix-now** (A2 must address before the JIT default-flip) or **defer** (real but
out of the epic's critical path). It changes no code -- it is the fix-list A2
(bd polyglot-pdf-jnjj.9) and the broader Pillar A work build from.

## Current JIT data flow (what actually happens today)

1. **Frontend builds a manifest** -- `manifestUtils.ts` `buildHandshakeManifest` ->
   `HandshakeManifest = {current_section, previous_sections, parts}` (section_id /
   section_label keys; `current_section.fields` = full field_id|spoken_name list).
2. **Frontend JIT handshake** -- `schemaFormState.ts::getJITHandshakePayload`
   (~621-647) sends `{type:"handshake_jit", manifest, first_field_schema,
   loaded_field_ids, current_values, resume, section_number, section_label,
   total_sections, fill_language}`. (Note it OMITS `section_id`,
   `initial_field_hint`, `previous_spoken_names` -- see
   [../standards/ws-protocol.md](../standards/ws-protocol.md) drift flags.)
3. **Backend parse** -- `websocket_routes.py` JIT branch (~653-669) reads only
   `manifest.parts` (-> `schema["parts"]`) and `first_field_schema` (->
   `schema["fields"] = [first_field_schema]`), stores the whole `manifest` in
   `schema["manifest"]`, and `loaded_field_ids` in `schema["loaded_field_ids"]`.
4. **Backend SI build** -- `ai_context.py` JIT branch (~280-336) calls
   `generate_part_manifest(schema, previous_parts_manifests=[])` over
   `schema["fields"]` (= one field) and `get_next_field_schema(schema,
   current_field_id=None)` (= `fields[0]`), then renders `{manifest_text}` +
   `{next_field_schema}` into `JIT_SYSTEM_INSTRUCTION`.

**The core incoherence:** the frontend builds a full-section manifest and sends it,
but the backend ignores `manifest.current_section` / `previous_sections` and
REGENERATES the manifest from `schema["fields"]` -- which in JIT mode is just the
first field. So the reduced SI today carries ONE field, not the section, and never
the previous sections. (Confirmed independently by Codex's F1 review, PR #202.)

## Gap catalog

Severity legend: **[BREAKS]** SI is wrong / model misled -- **[WASTE]** correctness
OK but tokens/turns wasted -- **[CLEAN]** cleanliness / robustness / dead code.

### Fix-now (A2 must address before the JIT default-flip)

- **A -- [BREAKS] Handshake manifest is ignored; backend regenerates from one
  field.** `websocket_routes.py:664-668` stores `manifest` but consumes only
  `manifest.parts`; `ai_context.py:284` regenerates via
  `generate_part_manifest(schema, ...)` over `schema["fields"]` (=
  `[first_field_schema]`, set at `websocket_routes.py:663`). The frontend's
  `current_section.fields` / `previous_sections` are dead on the wire. *Fix: consume
  the handshake manifest the client already sends, instead of regenerating from the
  synthesized single-field schema.* (F1-flagged.)
- **B -- [BREAKS] Rendered `{manifest_text}` lists only the first field, not the
  section.** Direct consequence of A: `manifest_service.py:37-42` iterates
  `schema["fields"]` (length 1). The SI claims to describe the section but covers 1
  of N fields. (F1-flagged.)
- **C -- [BREAKS] `previous_parts` is hardcoded empty -> no cross-section recall in
  the SI.** `ai_context.py:284` passes `previous_parts_manifests=[]`; the
  "PREVIOUS PARTS" block (`manifest_service.py:189-196`) is always empty. The model
  can only reach earlier-section values via the `get_field_value` tool, never the
  cheap manifest. (F1-flagged.)
- **D -- [WASTE] `{next_field_schema}` is the FIRST field, not first-UNFILLED.**
  `ai_context.py:288` -> `get_next_field_schema(schema, current_field_id=None)` ->
  `fields[0]` (`manifest_service.py:84-86`), ignoring `current_values`. On a
  reconnect / section revisit with earlier fields confirmed, the SI points at an
  already-filled field, and disagrees with `{next_field_hint}` (which the client
  computes correctly). *Fix: select the first unfilled field (consult
  current_values).* (F1-flagged.)
- **L -- [WASTE] Handshake `loaded_field_ids` is dropped -> schemas re-sent on
  reconnect.** `form_filling_service.py:55` inits `self._loaded_field_ids = set()`
  and only populates it at runtime (`:929`); the client's `loaded_field_ids` (which
  schemas Gemini already received, survives reconnects) is stored in
  `schema["loaded_field_ids"]` (`websocket_routes.py:665`) but NEVER seeded into
  `self._loaded_field_ids`. On a mid-session reconnect the de-dup resets, so
  already-sent field schemas are re-sent. *Fix: seed `_loaded_field_ids` from the
  handshake at session start.* (NEW -- not in the F1 contract.)
- **G -- [WASTE] The schema de-dup helper is dead code.**
  `should_include_schema_in_response` (`manifest_service.py:141-155`) is imported
  (`form_filling_service.py:23`) but has zero call sites -- the
  "don't re-send a schema Gemini already has" gate is never actually applied. Pairs
  with L: even within a session, the `loaded_field_ids` set isn't consulted via this
  helper. *Fix: wire the de-dup on the `confirm_field` inline-schema path, or remove
  the helper if A4 supersedes it.* (NEW.)

### Defer (real, but out of the epic's critical path)

- **E -- [CLEAN] Telemetry log reads a non-existent key.**
  `websocket_routes.py:671` logs `manifest_fields=len(manifest.get("fields", []))`,
  but the manifest has no top-level `fields` (it is `current_section.fields`), so it
  always logs 0. A symptom of A; fix alongside A or drop the line. (NEW.)
- **F -- [CLEAN] "part" terminology holdout in `manifest_service.py`.**
  `generate_part_manifest` / `current_part` / `part_id` / `part_label` / the
  "CURRENT PART:" SI text (`manifest_service.py` throughout) use part-language where
  the codebase uses section. EXPLICITLY DEFERRED per
  [../standards/terminology.md](../standards/terminology.md) (renaming changes the
  Gemini prompt wording -- behavior-adjacent). Note: when A2 reworks this file for A
  anyway, folding the rename in is reasonable, but it is not required by A1/A2.
- **H -- [CLEAN] `estimate_manifest_tokens` is test-only.**
  `manifest_service.py:201-224` is used only by tests; no production caller. The G2
  cost gate measures rendered SI tokens via `measure_form_session_costs.py` instead,
  so this estimator is redundant for the epic -- keep or drop, no behavior impact.
- **I -- [CLEAN] Options-formatting code is duplicated** between the legacy
  (`ai_context.py:169-198`) and JIT (`:304-315`) branches. Identical dict/string
  handling (and both are correct post-d24n). A shared helper would DRY it; pure
  cleanliness.
- **J -- [CLEAN] No handshake-shape validation on the JIT path.**
  `websocket_routes.py:654-655` reads `manifest` with no shape check; a `None`/
  malformed manifest fails late (e.g. `generate_part_manifest(None)` would
  `AttributeError`). The happy path is fine; a defensive validator (mirroring the
  legacy `invalid_schema` close at `:677-681`) would harden it.
- **K -- [CLEAN] Redundant manifest storage.** `schema["manifest"]` carries the full
  manifest that nothing consumes (only `schema["parts"]` and `schema["fields"]` are
  read). Once A fixes the consumption path, either consume the stored manifest or
  stop storing it -- today it is dead weight. (Resolves naturally with A.)

## A2 worklist (the fix-now set, in dependency order)

1. **Consume the handshake manifest** (A) so `{manifest_text}` lists the real
   section -- this is the keystone; B, E, K resolve with it.
2. **Populate `previous_parts`** (C) from the handshake's `previous_sections` so
   cross-section recall works in the cheap manifest.
3. **Select first-unfilled for `{next_field_schema}`** (D) -- consult
   `current_values`; reconciles with `{next_field_hint}`.
4. **Seed + honor `loaded_field_ids`** (L + G) -- seed `_loaded_field_ids` from the
   handshake and actually call the de-dup gate so schemas are sent once across
   reconnects.

The defer set (E cleanup, F rename, H/I/J/K cleanliness) can ride along where
convenient but does not gate the JIT default-flip. None of these are behavioral
measurements -- they precede G2/G3, which measure the RESULT of A2's fixes.
