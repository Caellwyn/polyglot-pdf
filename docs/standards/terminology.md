# Terminology canon

*Last updated: 2026-05-30. See [journal entries](../journal/entries/) for chronological history.*

**Tracks:** `backend/models/form_models.py` `backend/services/manifest_service.py` `frontend/src/schema-forms/state/schemaFormState.ts` `docs/schema_format.md`

The controlled vocabulary for polyglot-pdf. When code and docs disagree on a
word, **this file wins** -- align to it. Cross-cutting; read before naming a new
state variable, schema field, or log key.

## Part vs. Section vs. Field (the form hierarchy)

The schema is a strict hierarchy -- **Form > Parts > Sections > Fields** (see
[`schema_format.md`](../schema_format.md) and `FormSchema` in
`backend/models/form_models.py`). These are **distinct levels, not synonyms**:

| Term | What it is | In the model |
|------|-----------|--------------|
| **Field** | One fillable input (text, checkbox, date, signature, ...). | `FormField`; `id` like `p1_checkbox4[0]`. |
| **Section** | The **user-facing navigation unit** -- what the user moves between, what "switch section" targets. Always present. | `FormSection { id, label, fields: [field_id] }`; `FormSchema.sections` (required). |
| **Part** | An **optional higher-level grouping of sections** (e.g. "Part A: Information About Applicant" on a USCIS form). Not every form has parts. | `FormPart { id: "part_a", label, ... }`; `FormSchema.parts` (Optional); `get_sections_in_part()`. |

**Canon:**
- "**Section**" is the primary unit for navigation and conversation. Tool calls,
  state, and UI speak *sections* (`switch_section`, `currentSectionId`,
  `completedSections`).
- "**Part**" is reserved for the optional schema-level grouping above sections.
  Use it **only** when you mean that grouping -- never as a loose synonym for
  "section."

### The legacy "part" drift (do not propagate)

"Part" leaks into a few **state-variable names where a *section* is actually
meant** -- a naming bug, not a real part reference. Canonical state is
`currentSectionId` / `completedSections` (frontend) and section-keyed identifiers
(backend). The known holdouts, all meaning "current section":

- `backend/adapters/live_ai_gemini.py` -- `self._current_part_id`, the
  `current_part_id` ctor arg, and the `part_id=` log field (~lines 177, 227-238, 1231).
- `backend/utils/token_file_logger.py` -- `part_id` log arg (~lines 71, 99).
- `backend/services/form_filling_service.py:144` -- `current_part_id=None,
  # Will be updated on section switch` (the comment proves the conflation).
- `backend/services/manifest_service.py` -- `current_part`/`previous_parts` keys
  in the JIT manifest (here "part" is ambiguous with the real `FormPart`; treat
  as drift pending the manifest's own review).
- Frontend test fixture `frontend/src/schema-forms/state/schemaFormState.test.ts.NEEDS_SECTION_REFACTOR`
  (filename already flags it).

Don't add new `part_id`/`currentPartId` names for section state. Renaming the
holdouts is tracked in `polyglot-pdf-gfb.4` -- a behavior-preserving rename.
(The `manifest_service.py` keys are ambiguous with the real `FormPart`; that
bead reviews them rather than blindly renaming.)

## Field IDs and brackets

Field IDs can contain brackets -- e.g. `p1_checkbox4[0]` (PDF AcroForm array
notation). These are **passed through verbatim, not escaped**: the JIT manifest
deliberately emits them as-is to avoid JSON-quote confusion
(`backend/services/manifest_service.py`; `backend/tests/unit/test_ai_context.py`
asserts "field IDs with special characters (brackets) are not escaped"). When you
match, log, or forward a field ID, **keep the brackets**; don't strip or
backslash-escape them. Gemini is instructed to use the exact `field_id` from the
schema, brackets included (`backend/config.py`).

## form-session vs. session

Two different "sessions" -- keep them straight:

| Term | Scope | Identifier |
|------|-------|-----------|
| **form-session** | One user filling one form, end to end. **Survives WS reconnects and Gemini-session restarts.** Owns the field state in `sessionStorage`. | `formSessionId`, format `fss_<base36-ts>_<random>` (`schemaFormState.ts: generateFormSessionId`); sent to the backend as `form_session_id` for logging/metrics. |
| **session** (Gemini / WS) | One WebSocket connection / one Gemini Live session. A form-session may span **several** of these. | `session_id` on the backend (`LiveAIGemini`); not persisted client-side. |

So "the session reconnected" is ambiguous -- say **"the WS/Gemini session
reconnected (same form-session)"**. State persistence is a property of the
**form-session**, never the WS session.

## Stateless / state ownership

The client is the source of truth; the backend is stateless re: field values.
Documented in [`stateless-architecture.md`](stateless-architecture.md) (planned,
`polyglot-pdf-pki`) -- cross-referenced here because "session state" above means
*client-owned* state.
