# Audit: naive / JIT / DTI arm coexistence (bd polyglot-pdf-fu1h)

*Date: 2026-06-27. Investigate/document bead for epic polyglot-pdf-13w7 (fully-static
DTI SI). Read against dev @ 2a44fa72 (1ac3 + j748 merged; uogm + h1bn still open).
Every finding below was verified against the cited code, not inferred.*

## Why this audit

The form-context / system-instruction (SI) architecture runs **three parallel arms**
that SHARE surfaces, and DTI is a major overhaul that is only half-landed (1ac3 +
j748 merged; uogm + h1bn pending). Before more code lands on the shared surfaces,
this enumerates the coexistence conflicts so uogm (C) and h1bn (D) build on known
terrain. The three arms:

| Arm | Flag | SI template | Field delivery |
|-----|------|-------------|----------------|
| **naive / legacy** | both off (default) | `SYSTEM_INSTRUCTION` | full per-section field dump in the SI |
| **JIT** | `USE_JIT_SCHEMA` | `JIT_SYSTEM_INSTRUCTION` | manifest (id|name pairs) + one field schema in the SI |
| **DTI** | `USE_DTI` | `DTI_SYSTEM_INSTRUCTION` (now fully static) | NO field data in the SI; field 1 via the initiating message, fields 2..N via the confirm_field response |

All three default OFF (`backend/config.py:119,128`), so production today is the naive
arm. DTI/JIT are experimental.

## The shared surfaces (where the arms can collide)

1. **`build_form_context` 3-way branch** (`backend/services/ai_context.py`): DTI at
   `:368` -> JIT at `:400` (`elif USE_JIT_SCHEMA or schema.jit_mode`) -> legacy `else`
   at `:500`. Precedence is **DTI > JIT > legacy**, mutually exclusive at the SI level.
2. **The SI templates + shared initiating-message templates** (`backend/config.py`):
   `SYSTEM_INSTRUCTION` (:372), `JIT_SYSTEM_INSTRUCTION` (:434), `DTI_SYSTEM_INSTRUCTION`
   (:504), and `INITIATING_MESSAGE` / `RESUME_INITIATING_MESSAGE` /
   `DISCLAIMER_INITIATING_MESSAGE` (:579-597), which ALL three arms share for the opener.
3. **Two handshake shapes** (`backend/routes/websocket_routes.py:699-748`): `handshake`
   (full schema) vs `handshake_jit` (manifest + first_field_schema + `jit_mode:true`).
4. **The client-driven opener** (`change_spoken_language` -> `send_initiating_message`),
   plus the section-switch opener (`form_filling_service.py:846-852`).
5. **`_dti_extra_fields` vs `_schema["fields"]`** (DTI validation/lookup set vs current-field source).
6. **The compression-window derivation** (`backend/adapters/live_ai_gemini.py:1217-1222`):
   `CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR AND USE_DTI` derives the window from the SI
   floor. DTI-gated, so it is a shared surface only the DTI arm touches. See F8 (benign).

## Severity legend

- **BLOCKER-FOR-C/D** -- must be handled by uogm or h1bn or that bead ships a bug.
- **LATENT** -- real, can bite under a specific scenario, but not on the default path today.
- **BENIGN / BY-DESIGN** -- noted so it is not re-investigated.

---

## Findings

### F1. Section switch sends NO manifest -> DTI progress/metadata block will be empty after a switch -- **BLOCKER-FOR-C (uogm)**

**Scenario.** A section switch sends `extractSectionFields` (the new section's FULL
field list) with NO `manifest` key, on BOTH switch payloads: the AI-initiated
`section_info_response` (`frontend/src/webFormConnection.ts:1086`,
`schema: sectionSchema`) and the manual `manual_section_switch`
(`webFormConnection.ts:2435-2438`, `schema: sectionSchema`). It is consumed at the
`backend/routes/websocket_routes.py` switch handler -> `form_filling_service.py:802`
`build_form_context_message(section_schema, ...)`. The DTI branch reads
`schema.get("manifest") or {}` (`ai_context.py:369`), so on a switch
`current_section = {}` and `section_fields = []` for either payload.

**Why it matters for C.** Today this is benign for DTI because the static SI **discards**
the computed progress (`ai_context.py:374-392` computes `total_fields`/`filled_count`
then returns the bare constant). But uogm's whole job is to move `fill_language` +
form/section metadata + progress + previous-names + confirmation-policy ONTO the
injection. If uogm builds a `render_section_metadata` block from the manifest the way
the initial connect supplies it, that block will be **empty after every section switch**
(no manifest in the switch payload), so the model loses the section header/progress on
section 2..N. uogm must either (a) build the metadata block from `section_metadata`
(which the switch DOES carry: section_number/label/total/previous_spoken_names at
`form_filling_service.py:805-808`) rather than from the manifest, or (b) have the
frontend include a manifest on the switch payload.

**Note:** field-1 GUIDANCE at switch is fine (see F2) -- this is specifically the
progress/metadata channel, which is C's surface.

Evidence: `webFormConnection.ts:1048`, `form_filling_service.py:802-808`,
`ai_context.py:369-392`.

---

### F2. DTI field-guidance resolution at session start AND section switch is CORRECT today -- **BENIGN (confirms j748 holds across arms)**

**Verified working**, recorded so it is not mistakenly "fixed":
- Initial connect: DTI sends `handshake_jit` (because `jit_mode_enabled = USE_JIT_SCHEMA
  OR USE_DTI`, `websocket_routes.py:814`; the frontend sends `handshake_jit` when
  `jitModeEnabled`, `schemaFormState.ts:594`), so `first_field_schema` is the
  `computeNextField` (first-unfilled) field (`schemaFormState.ts:636`). The opener's
  hint carries `(field_id: '...')`; `send_initiating_message._resolve_hint_field_schema`
  finds it in `_schema["fields"]` + `_dti_extra_fields` -> renders the right field.
- Section switch: `start_session(schema=section_schema)` sets `self._schema` to the
  new section's full fields, and the switch opener (`form_filling_service.py:851`) passes
  `initial_field_hint = computeNextFieldHintString()` (carries the id), so the hint
  resolves against the new `_schema["fields"]`. `_dti_extra_fields` is reset on
  `start_session` (`form_filling_service.py:181`), so no cross-section staleness.

Evidence: `schemaFormState.ts:594,636`; `form_filling_service.py:181,335-359 (resolver),851`.

---

### F3. Stale-persisted-mode window: the FIRST handshake after a backend flag flip uses the OLD mode -- **LATENT (partly mitigated by design)**

**Scenario.** `jitModeEnabled` is persisted in sessionStorage (`schemaFormState.ts:35`,
survives reload/reconnect); `dtiModeEnabled` is in-memory only on the connection
(`webFormConnection.ts:98,520`). The handshake is sent in `handleOpen` BEFORE
`session_ready` reports the backend's actual flags (`handleSessionReady` at
`webFormConnection.ts:503-520` runs after the send). So if the maintainer flips
`USE_JIT_SCHEMA`/`USE_DTI` between sessions, the next connect's FIRST handshake uses the
stale persisted mode; reconciliation only takes effect on the SUBSEQUENT connect.

**Why partly mitigated.** The backend was hardened for exactly this: a `jit_mode`-shaped
handshake renders via the manifest branch EVEN when both flags are off
(`ai_context.py:400` `or schema.get("jit_mode")`, Codex PR #229), so a stale
`handshake_jit` against a flags-off backend still renders the section rather than a
1-field legacy dump. The reverse (stale legacy `handshake` against a DTI-on backend)
hits the DTI branch with a FULL-section `schema["fields"]` -- field-1 guidance still
resolves (the field is in the list), but there is no manifest so progress is absent
(same channel as F1).

**Why it stays LATENT not blocker.** All flags are off in production; this only bites
during an A/B flip, and the worst case is one degraded session that self-corrects on
reconnect. h1bn (edge cases) should add a reconnect/flag-flip note; not a code blocker.

Evidence: `webFormConnection.ts:98,376-377 (send),503-520 (learn)`;
`schemaFormState.ts:35,594`; `ai_context.py:400`.

---

### F4. `dtiModeEnabled` is in-memory only; a page reload before `session_ready` defaults it false -- **LATENT**

**Scenario.** `dtiModeEnabled` (`webFormConnection.ts:98`) is NOT persisted (unlike
`jitModeEnabled`). It gates whether the client attaches `next_field_schema` to
`next_field_hint_response` (`webFormConnection.ts:861`), which is what populates the
backend `_dti_extra_fields` for fields 2..N. On a page reload mid-form, until the new
`session_ready` arrives, `dtiModeEnabled` is false, so any `next_field_hint_response`
sent in that window omits the schema -> that field is NOT recorded in `_dti_extra_fields`
-> a later opener/language-change at that field cannot resolve its guidance (renders
nothing; the model falls back to the spoken hint + static SI).

**Why LATENT.** The window is small (reload -> session_ready) and the failure mode is
graceful (no guidance block, not a wrong block). Worth an h1bn edge-case note;
optionally persist `dtiModeEnabled` alongside `jitModeEnabled` for symmetry.

Evidence: `webFormConnection.ts:98,520,861`.

---

### F5. `USE_JIT_SCHEMA` + section switch loses the JIT manifest -- **BENIGN for the epic (JIT-arm, pre-existing)**

**Scenario.** With `USE_JIT_SCHEMA=true` (DTI off), a section switch sends full fields
(no manifest), so the JIT branch (`ai_context.py:400`) reads an empty manifest and the
JIT SI's `{manifest_text}` renders empty for the switched section.

**Why BENIGN for THIS epic.** This is a property of the **JIT arm**, which the static-SI
epic does not touch (epic is DTI-only; DTI takes precedence so this branch never fires
when `USE_DTI=true`). It is a pre-existing JIT limitation, not introduced or worsened by
1ac3/j748/uogm/h1bn. Recorded for completeness; out of epic scope. (If the JIT arm is
ever revived as a shipping path, file a dedicated bead -- not needed now.)

Evidence: `ai_context.py:400-419`, `form_filling_service.py:802`.

---

### F6. Both flags on (`USE_JIT_SCHEMA=true` AND `USE_DTI=true`) -- **BENIGN (precedence safe), but unguarded config**

DTI precedence (`ai_context.py:368` before `:400`) means DTI wins cleanly; the JIT
manifest rides along unused. No corrupted/mixed SI. This is a config mistake, not a
supported state, and nothing crashes. **Optional hardening (not a blocker):** a startup
warning if both flags are true would make the mistake visible. The config comment
(`config.py:126` "Mutually exclusive with USE_JIT_SCHEMA at the SI level") documents the
intent but does not enforce it.

Evidence: `ai_context.py:368,400`; `config.py:126`.

---

### F7. `DISCLAIMER_INITIATING_MESSAGE` does NOT take `{current_field_guidance}` -- **BENIGN (verified safe)**

j748 added `{current_field_guidance}` to `INITIATING_MESSAGE` + `RESUME_INITIATING_MESSAGE`
only. `DISCLAIMER_INITIATING_MESSAGE` is `.format`ed with just `spoken_language` +
`disclaimer_text` and has no field placeholder, so it is unaffected and correctly fires
PRE-disclaimer (no field prompt before the legal disclaimer -- the exact issue Codex
flagged on PR #254). Verified the only `.format` callers of the two field-bearing
templates are inside `send_initiating_message` (which passes all three kwargs).

Evidence: `config.py:579-597`; `form_filling_service.py:415-419`.

---

### F8. Compression-window derivation is gated on `USE_DTI` -> uogm changing SI size shifts it automatically -- **BENIGN (no action; note for C)**

**Scenario.** The context-compression window is derived from the SI floor only when
`CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR AND USE_DTI`
(`backend/adapters/live_ai_gemini.py:1217-1222` -> `derive_compression_window` at
`:170`). uogm changes what the DTI SI + injection carry, which changes the SI floor.

**Why BENIGN.** The derivation reads the floor at session build time, so it tracks any
SI-size change automatically -- there is nothing for uogm to update, and the gate is
DTI-only so legacy/JIT are untouched. Recorded so C's implementor does NOT file a
separate "did I break compression sizing?" concern: they did not, it self-adjusts.
(If uogm moves a LOT onto the injection such that the per-turn injection dwarfs the SI,
h1bn's cost measurement will catch any window mis-sizing -- already in its scope.)

Evidence: `live_ai_gemini.py:170,1217-1222`.

---

## Go / no-go for the remaining epic children

- **uogm (C) -- GO, with one required design constraint (F1).** Build the
  `render_section_metadata` block from the **section_metadata the switch already carries**
  (section_number/label/total/previous_spoken_names), NOT from `schema["manifest"]` --
  otherwise the metadata/progress block is empty after every section switch. `fill_language`
  riding `render_field_guidance` is unaffected (it travels with each field render, which
  resolves correctly per F2). This constraint is recorded directly on the **uogm bead notes**.

- **h1bn (D) -- GO.** Its existing scope (reconnect/resume, section switch,
  restart_gemini_session, race safety, >=10 live runs) already covers the LATENT items.
  F3 (flag-flip reconnect) and F4 (dtiModeEnabled reload window) are added to its
  verification list via the **h1bn bead notes**.

No finding blocks the epic outright. The DTI happy path (initial connect + section
switch + fields 2..N) is verified correct today (F2); the real work for C is the
metadata channel's section-switch source (F1).

## Disposition (no orphan beads filed)

This audit found **no shipped-code defect** -- every actionable item is a *constraint on
an upcoming epic child*, so each is recorded on the bead that will act on it rather than
as a standalone bead (which would just duplicate the child):

- **F1 -> uogm notes** (the metadata-source constraint; must-do for C).
- **F3 + F4 -> h1bn notes** (added to D's edge-case verification list).
- **F2, F5, F6, F7, F8** are BENIGN/by-design and explicitly marked so they are not
  re-investigated. F6 (both-flags-on) and F7 have optional, non-blocking hardening
  ideas noted inline; neither warrants a bead now. F8 (compression-window derivation)
  self-adjusts to uogm's SI-size change -- no action, noted so C does not re-raise it.

The optional "both flags on -> startup warning" hardening (F6) is the only thing that
could be a future bead; deliberately NOT filed (config mistake, not a real risk while
flags are off). If the JIT arm is ever revived as a shipping path, F5 would warrant a
dedicated bead -- also not now.
