# Terminology canon

*Last updated: 2026-07-09. See [../journal/entries/2026-07-09-bd-5f41-p2-1-option-pdf-position-model-backfill-tool-kit.md](../journal/entries/2026-07-09-bd-5f41-p2-1-option-pdf-position-model-backfill-tool-kit.md) for closeout details.*

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
| **Section** | The **user-facing navigation unit** -- what the user moves between, what "switch section" targets. Always present. | `FormSection { id, label, order, fields: [field_id] }` (`order` is required and drives navigation sequence); `FormSchema.sections` (required). |
| **Part** | An **optional higher-level grouping of sections** (e.g. "Part A: Information About Applicant" on a USCIS form). Not every form has parts. | `FormPart { id: "part_a", label, ... }`; `FormSchema.parts` (Optional); `get_sections_in_part()`. |

**Canon:**
- "**Section**" is the primary unit for navigation and conversation. Tool calls,
  state, and UI speak *sections* (`switch_section`, `currentSectionId`,
  `completedSections`).
- "**Part**" is reserved for the optional schema-level grouping above sections.
  Use it **only** when you mean that grouping -- never as a loose synonym for
  "section."

### The legacy "part" drift (do not propagate)

"Part" leaked into **state-variable names where a *section* is actually
meant** -- a naming bug, not a real part reference. Canonical state is
`currentSectionId` / `completedSections` (frontend) and section-keyed identifiers
(backend).

The **internal** holdouts were renamed to section-canonical names in
`polyglot-pdf-gfb.4` (behavior-preserving): `live_ai_gemini.py`'s
`self._current_section_id` + the `current_section_id` parameter of
`set_session_context()`, and the `form_filling_service.py` call site.

**Wire-format renames done in `polyglot-pdf-zun`:**

- `backend/utils/token_file_logger.py` -- the payload key is now `section_id` (was
  `part_id`); the producer (`live_ai_gemini.py`) passes `section_id=self._current_section_id`.
  `token_usage.jsonl` events now carry the active section under `section_id`
  (tb7 also fixed the **value**, which was permanently null before).
- `frontend/src/schema-forms/utils/manifestUtils.ts` -- the JIT handshake manifest's
  section keys are now section-canonical: `current_section`/`previous_sections`/
  `section_id`/`section_label` (was `current_part`/`previous_parts`/`part_id`/
  `part_label`). This rename is **frontend-internal**: the Python backend
  (`backend/routes/websocket_routes.py`) consumes only `manifest.parts` (the section
  navigation list, already section-canonical `{id, order, label}`), NOT the
  `current_part`/`part_id` keys -- so it was not a both-ends-lockstep change.

**Remaining `part`-named holdout (intentionally out of zun scope):**

- `backend/services/manifest_service.py` `generate_part_manifest` / `format_manifest_for_context`
  -- a SEPARATE backend-internal path feeding `ai_context.py` system-instruction text
  ("CURRENT PART: ..."). It still emits `current_part`/`part_id`/`part_label`. Renaming
  it changes the Gemini prompt wording (behavior-adjacent), so it is deferred; it is
  not on either wire format. The `parts` navigation key (consumed by the backend) keeps
  its name because that IS the backend wire contract.

Don't add new `part_id`/`currentPartId` names for section state.

## Schema v2 group + conditional vocabulary (bd h76m.3)

`FormSchema.schema_version` selects the dialect: `None`/`"1"` is the legacy
tolerant read (every shipped kit today); `"2"` opts in to the strict rules
below (enforced at parse by `form_models.py`, matrix defined in
`backend/models/conditional_vocabulary.py` -- the registry is the source of
truth, never a hand-copied list). Until the strictness flip (epic h76m P6.2)
both dialects parse.

| Term | Meaning in v2 |
|------|---------------|
| **checkbox** | A STANDALONE boolean field. `options` are **forbidden** on it. Never a group. |
| **checkbox_group** | ONE logical multi-select question; the only group mechanism is its `options[]`. Value shape is a `List[str]` of option slugs. No field-level `pdf_field_name`; per-box PDF identity lives on `options[].pdf_field_name` (+ `pdf_on_value`, + the per-option `pdf_position` rect since bd polyglot-pdf-5f41). |
| **radio** | Single-select choice field (value is one option slug). PDF mapping is per-option `pdf_field_name` OR a shared field-level `pdf_field_name` + per-option `pdf_on_value` (true-AcroForm kids); each option may also carry its own `pdf_position` rect (bd polyglot-pdf-5f41). |
| **option slug** | `FieldOption.value` in v2: a SEMANTIC slug minted deterministically from the label (lowercase ascii `[a-z0-9_-]`, no commas/spaces, unique per field, immutable once minted). Widget identity never lives in `value`. |
| **ConditionGroup** | The composite condition: one level of `all_of` / `any_of` / `none_of` buckets of atomic `{field, operator, value}` conditions. Flat by construction -- no nesting. "(A AND B) AND NOT C" = `all_of:[A,B] + none_of:[C]`. |
| **require_if** | Field-level condition (same shape as `show_if`) under which the field becomes REQUIRED. Replaces `controls_fields.makes_required`. |
| **includes / not_includes** | Group-membership operators: "option slug X is (not) in the checkbox_group trigger's selected set". In v2, `equals` on a group trigger is a validation ERROR -- the undocumented equals-means-membership evaluator hack (bd vq4m) is retired vocabulary. |
| **is_checked** | Bool sugar on a standalone checkbox ONLY. "Any box of the group ticked" is `is_not_empty` (the is_checked dual fate -- `backend/tests/fixtures/is_checked_dual_fate.json`). |

RETIRED vocabulary (all DELETED at the P6.2 strictness flip, bd
polyglot-pdf-h76m.16): `controls_fields` / `ConditionalControl` (trigger-side
action lists; were dead at runtime -- the migration mirrored their
`shows`/`makes_required` into target-side `show_if`/`require_if`),
`conditional_fields`, and `group_kind`/`GroupKind` are all removed from the model
-- a schema carrying `controls_fields`/`conditional_fields` has the key silently
ignored (extra="ignore"), and a checkbox group is now identified by its TYPE (the
v2 `checkbox_group`, or a legacy `checkbox` with options[]), never `group_kind`.
`consolidated_widgets` was never a modeled field (it appears only in kit JSON /
SI-exclusion lists). The vq4m equals-means-membership evaluator hack + the
comma-split tolerance are also gone from both evaluators (membership is
`includes`/`not_includes` only).

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
Documented in `stateless-architecture.md` (`polyglot-pdf-pki`) -- cross-referenced
here because "session state" above means *client-owned* state. (Plain reference,
not a link, until that doc lands on `dev`.)
