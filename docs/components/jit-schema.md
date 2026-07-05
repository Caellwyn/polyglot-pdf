# JIT schema loading -- infra (audit + A2 repair)

**Tracks:** backend/services/manifest_service.py backend/services/ai_context.py backend/routes/websocket_routes.py backend/services/form_filling_service.py backend/services/callback_handler.py backend/config.py frontend/src/schema-forms/utils/manifestUtils.ts frontend/src/schema-forms/state/schemaFormState.ts

*Last updated: 2026-07-05 (bd polyglot-pdf-mpoe staleness sweep: re-verified every claim against current code -- no behavioral drift; refreshed stale line-number citations, added callback_handler.py + config.py to Tracks, and noted the JIT handshake now also carries full_schema for the secretary agent). See [../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md](../journal/entries/2026-07-05-bd-mpoe-doc-staleness-sweep.md).*

The JIT path (`USE_JIT_SCHEMA=true`, default OFF) was built by weaker models, audited
under A1, and repaired under A2. This doc is the audit catalog: the **fix-now** gaps
(below, marked REPAIRED) are now closed; the **defer** gaps remain live cleanup. The
"Current JIT data flow" section below describes the path AFTER the A2 repair.

## Current JIT data flow (what actually happens today)

1. **Frontend builds a manifest** -- `manifestUtils.ts` `buildHandshakeManifest` ->
   `HandshakeManifest = {current_section, previous_sections, parts}` (section_id /
   section_label keys; `current_section.fields` = full field_id|spoken_name list).
2. **Frontend JIT handshake** -- `schemaFormState.ts::getJITHandshakePayload`
   sends `{type:"handshake_jit", manifest, first_field_schema, loaded_field_ids,
   current_values, resume, section_number, section_label, total_sections,
   fill_language, form_title, previous_spoken_names, initial_field_hint, full_schema}`.
   `first_field_schema` is the FIRST-UNFILLED field's schema (via `computeNextField`),
   not `fields[0]` (A2 fixed gap D). The form_title / previous_spoken_names /
   initial_field_hint were added by A2 (gaps O/M/D-hint -- the JIT handshake used to
   under-send them). `full_schema` (the WHOLE form, all sections) rides every
   handshake for the secretary agent's catalog (bd polyglot-pdf-p68s/jnjj.45d) --
   it is not consumed by the JIT SI-build path itself, only by the secretary.
3. **Backend parse** -- `websocket_routes.py` JIT branch reads `manifest.parts`
   (-> `schema["parts"]`), `first_field_schema` (-> `schema["fields"] =
   [first_field_schema]`), the whole `manifest` (-> `schema["manifest"]`),
   `loaded_field_ids` (-> `schema["loaded_field_ids"]`), and `form_title`
   (-> `schema["form_metadata"]["title"]`, A2 gap O).
4. **Backend SI build** -- `ai_context.py` JIT branch CONSUMES the client manifest:
   `{manifest_text}` is built from `manifest.current_section.fields` +
   `manifest.previous_sections` (A2 gaps A/B/C), `filled_count`/`total_fields` are
   computed from the real section field set (gap N), and `{next_field_schema}`
   renders the client-sent first-unfilled field's schema (gap D). The de-dup gate
   (`should_include_schema_in_response`) now actually fires in
   `form_filling_service.get_next_field_schema_for_jit`, seeded from the handshake's
   `loaded_field_ids` (gaps G/L; bug polyglot-pdf-h2ii).

**The core incoherence (REPAIRED by A2):** the frontend builds a full-section
manifest and sends it; the backend used to ignore `manifest.current_section` /
`previous_sections` and REGENERATE from `schema["fields"]` (= one field in JIT mode),
so the reduced SI carried ONE field, not the section. A2 made the backend consume the
client manifest. (The pre-fix incoherence was confirmed independently by Codex's F1
review, PR #202.)

## Gap catalog

Severity legend: **[BREAKS]** SI is wrong / model misled -- **[WASTE]** correctness
OK but tokens/turns wasted -- **[CLEAN]** cleanliness / robustness / dead code.

### Fix-now -- ALL REPAIRED by A2 (bd polyglot-pdf-jnjj.9)

> Every gap in this subsection (A, B, C, D, E, G, L, M, N, O) was fixed by A2; see
> the journal entry. The entries below are retained as the record of WHAT was wrong
> and where; the "Current JIT data flow" section above describes the repaired state.

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
  already-filled field. *Fix: select the first unfilled field (consult
  current_values).* (F1-flagged.) **Note both next-field placeholders are wrong in
  JIT mode, not just this one:** the JIT handshake ALSO omits `initial_field_hint`
  (`schemaFormState.ts:635-647`), so `{next_field_hint}` falls back to the generic
  "the first unfilled field" string (`ai_context.py:333`; `websocket_routes.py:694`
  reads it as `None`) rather than the client's computed hint. A2 must fix BOTH the
  schema and the hint for JIT.
- **O -- [BREAKS] `{form_title}` always renders the literal "Form" in JIT mode.**
  `ai_context.py:139` reads `schema.get("form_metadata", {}).get("title", "Form")`,
  but the JIT schema dict (`websocket_routes.py:661-669`) has no `form_metadata` key
  and the JIT handshake sends no title (`schemaFormState.ts:635-647`). So the SI
  header is "Medical assistant: Form | Section N/M..." for EVERY form -- the model
  never learns which form (I-90, I-485, ...) it is filling, so it cannot name the
  form to the user or disambiguate by form. Same class as M/N/D: a JIT placeholder
  reading data the handshake does not carry. *Fix: send the form title on the JIT
  handshake.* (NEW -- fresh-eyes round 2.)
- **M -- [BREAKS] `{previous_spoken_names}` is always empty in JIT mode ->
  cross-section `get_field_value` lookups break.** A SEPARATE cross-section-recall
  path from Gap C (which is the manifest's PREVIOUS PARTS block). The JIT handshake
  omits `previous_spoken_names` (`schemaFormState.ts:635-647`; the legacy builder
  sends it at `:611`), so `previous_names_text` renders "None (this is the first
  section)" on EVERY section (`ai_context.py:257-264`). The model is told there are
  no prior-section fields to look up, so it cannot recall earlier values by spoken
  name even though the tool exists. Fixing Gap C alone does NOT fix this -- they are
  two independent SI mechanisms. *Fix: send `previous_spoken_names` on the JIT
  handshake.* (NEW -- fresh-eyes, not in the F1 contract.)
- **N -- [BREAKS] `{filled_count}/{total_fields}` progress is always wrong in JIT
  mode.** `total_fields = len(schema.get("fields", []))` (`ai_context.py:140`) and
  the `filled_count` loop (`:93-112`) both iterate `schema["fields"]`, which in JIT
  mode is `[first_field_schema]` (length 1). So the SI's "Progress: {filled_count}/
  {total_fields}" (`config.py:369`) is "0/1" or "1/1" for EVERY section regardless
  of real size -- the model is misled about how much of the section remains. A
  SEPARATE code path from the manifest (Gap A/B), so consuming the handshake
  manifest does not auto-fix it. *Fix: compute filled/total from the real section
  field set, not the synthesized one-field schema.* (NEW -- fresh-eyes.)
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
  helper. *Fix: gate `get_next_field_schema_for_jit` (`form_filling_service.py:900-933`)
  on `should_include_schema_in_response(...)` -- return None when already loaded.*
  **Also tracked as bug `polyglot-pdf-h2ii`** (found independently by the uov.16
  green-test re-audit), which adds the `confirm_field`-RETRY repro (a second confirm
  on the same field re-delivers the schema -- the 0y7 no-value-retry path) and
  requires a real, non-mocked-getter test. G + L are the same defect as h2ii from two
  audits; A2 (jnjj.9) implements the fix and must satisfy h2ii's exit criterion,
  covering BOTH the reconnect (L) and retry (h2ii) duplication paths.

### Discovered post-A2 (NOT repaired by jnjj.9)

- **P -- [SUPERSEDED by DTI / bd jnjj.22] The runtime next-field drip returns None
  for every field past the first, so the model never receives schemas for fields
  2..N.** RESOLUTION: not fixed in place -- REPLACED. Dynamic Turn Injection
  (USE_DTI, default OFF like USE_JIT_SCHEMA -- the two flags are independent and
  both gate off by default) drops the drip entirely; the next field's guidance is
  CLIENT-SUPPLIED on next_field_hint_response and rendered into the confirm_field
  response (response["next_field_guidance"]) by `callback_handler.py` (the single
  call site is gated on `next_hint` truthy, with the render itself gated on
  `USE_DTI`), honoring the stateless/client-owns-state invariant the drip
  violated. get_next_field_schema_for_jit remains only for the legacy JIT
  (USE_JIT_SCHEMA) arm. Original diagnosis below.
  A2 fixed the SI-BUILD path (gaps A/B/C/...) to consume the handshake manifest,
  but the separate RUNTIME drip was not touched. On each successful update/confirm,
  `callback_handler` calls `form_filling_service.get_next_field_schema_for_jit(field_id)`
  (single call site, `callback_handler.py:854-855`; the result is inserted into
  the tool response at `:917-918`) to compute the next field's full schema. That
  delegates to
  `manifest_service.get_next_field_schema(part_data=self._schema, current_field_id)`
  (`form_filling_service.py:935-938`), which finds "next" by INDEX within
  `part_data["fields"]` (`manifest_service.py:78-94`) -- it never consults the
  manifest. But in JIT mode `self._schema["fields"]` is `[first_field_schema]`
  (length 1, `websocket_routes.py:671`), so the index lookup returns
  `current_index+1 >= len(fields)` -> None for EVERY field. Nothing ever appends
  loaded fields back into `self._schema["fields"]`. Net effect: the model gets
  field 1's schema, then flies blind for fields 2..N -- distinct from Gap D (the
  SI's `{next_field_schema}` placeholder); this is the per-confirm tool-response
  drip. **G2 live evidence (bd polyglot-pdf-jnjj.6):** the `section-reset-jit`
  cost arm confirmed only 2/20 (happy) / 1/20 (unhappy) fields vs the full-SI
  baseline's 17/20 / 20/20, and cost MORE in real dollars (the non-advancing loop
  bloats the transcript past the SI savings). Verified empirically (drip returned
  None after firstName/middleName/lastName/preferredName) and by code path. *Fix:
  resolve the next field from the manifest's full field list
  (`current_section.fields`), then look its full schema up in the source part
  schema, rather than indexing `self._schema["fields"]`.* **Tracked as bug
  `polyglot-pdf-jnjj.22`; A5 (jnjj.12) is BLOCKED BY it.** (NEW -- G2 cost spike,
  bd jnjj.6.) See [../../scripts/spikes/jnjj_g2_jit_cost_findings.md](../../scripts/spikes/jnjj_g2_jit_cost_findings.md).

### Defer (real, but out of the epic's critical path)

- **E -- [CLEAN, but fix DURING A2] Telemetry log reads a non-existent key.**
  `websocket_routes.py:671` logs `manifest_fields=len(manifest.get("fields", []))`,
  but the manifest has no top-level `fields` (it is `current_section.fields`), so it
  always logs 0. A symptom of A. Tagged CLEAN because it changes no behavior -- BUT
  fresh-eyes correctly flags an operational hazard: A2 will be DEBUGGED against this
  log, and a manifest-field count stuck at 0 actively misleads during the very fix
  cycle that touches the manifest. So fix it AS PART OF A (when A2 reworks the
  manifest consumption, point the log at the real field count or drop it), not as a
  separate later cleanup.
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

The keystone insight: **the JIT handshake under-sends, and the backend reads
`schema["fields"]` (one field) for several independent SI pieces.** Fixing the
manifest path alone leaves the spoken-names, progress-count, and next-hint pieces
broken -- they read the same one-field schema through DIFFERENT code paths. A2 must
fix each.

1. **Consume the handshake manifest** (A) so `{manifest_text}` lists the real
   section -- the keystone; B, E, K resolve with it (fix the E log line here too).
2. **Populate `previous_parts`** (C) from the handshake's `previous_sections` so
   cross-section recall works in the cheap manifest.
3. **Send + render `previous_spoken_names` in JIT mode** (M) -- a SEPARATE
   cross-section path from C; without it `get_field_value` lookups for prior sections
   are dead even after C.
4. **Fix the JIT progress count** (N) -- compute `filled_count`/`total_fields` from
   the real section field set, not the one-field `schema["fields"]`.
5. **Select first-unfilled for both next-field placeholders** (D) -- the
   `{next_field_schema}` (consult current_values) AND `{next_field_hint}` (send
   `initial_field_hint` on the JIT handshake); both are wrong in JIT today.
6. **Send the form title + `previous_spoken_names` + `initial_field_hint` on the JIT
   handshake** (O + the handshake halves of M and D) -- a cluster of "the JIT
   handshake under-sends" fixes: today it omits the form title (`{form_title}` ->
   literal "Form"), `previous_spoken_names`, and `initial_field_hint`. Fix the
   handshake payload once to carry all three.
7. **Seed + honor `loaded_field_ids`** (L + G) -- seed `_loaded_field_ids` from the
   handshake and actually call the de-dup gate so schemas are sent once across
   reconnects.

The defer set (F rename, H/I/J/K cleanliness) can ride along where convenient but
does not gate the JIT default-flip. (E is now folded into step 1.) None of these are
behavioral measurements -- they precede G2/G3, which measure the RESULT of A2's fixes.
