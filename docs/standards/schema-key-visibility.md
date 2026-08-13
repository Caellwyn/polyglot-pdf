# Schema-key visibility matrix -- which model sees what

*Last updated: 2026-08-13 (bd polyglot-pdf-kbkd: VoiceOverlay.tsx's progress-counter sites migrated onto getProgressCounts; VoiceOverlayMobile.tsx's inventory line deliberately left unmigrated).*

Two models read the form and they must read **different** things. This doc is the
single answer to "if I add a key to a form-kit schema, who sees it?"

Asserted by `backend/tests/unit/test_52qm4_secretary_visibility_boundary.py`
against the shipped W-7 kit -- if you change a row here, change that test.

This is the key-level detail under the broader INCLUDE/EXCLUDE contract in
[`validation-delegation.md`](validation-delegation.md); that doc says what the
secretary is *for*, this one says which keys reach it.

## The two surfaces

| Surface | Built by | Scope | Cost profile |
|---------|----------|-------|--------------|
| **Voice SI** (Live model) | `manifest_service.get_field_guidance` -> `ai_context.render_field_guidance` | the CURRENT field only (DTI) | per-turn text-in = **95-98% of session cost** ([`logging-and-cost.md`](logging-and-cost.md)) |
| **Secretary context** (text model) | `secretary_context.render_static_catalog` + `render_values_tail` | the WHOLE form + verbatim booklet | cheap model, implicit-cache prefix |

The asymmetry is the point: the expensive realtime model gets one field; the
cheap text model carries the reference floor. A form-level leak into the voice SI
is a **cost** bug, not a tidiness one.

## The matrix

| Schema key | Voice SI | Secretary | Notes |
|---|---|---|---|
| `id` | YES | YES | the model must copy it verbatim (strict-id matching) |
| `spoken_name` | YES | YES | translated at runtime via `spoken_name_overrides` (bd `tupu.2`) |
| `name` / label | YES | YES | |
| `type` | YES | YES | |
| `validation.required` | YES | via `shown`/values tail | rendered as `Required: true` |
| `validation.format`, `min`/`max`, `*_length` | YES | no | steering hints only |
| `validation.pattern` / regex | YES | no | steering hint, rendered as `pattern: <regex>` in the per-field voice block (`ai_context.render_field_guidance`) |
| `options[].value` | YES | YES | the token the validator accepts -- rendered as `(use value: X)` |
| `options[].label` | YES | YES | translated via `option_label_overrides` (bd `ow1e`) |
| `options[].spoken_label` | YES | YES | stripped when a translation override applies |
| `help.instructions` | YES | YES | |
| `help.format_hint` | YES | YES | |
| `help.details` | YES (clamped) | YES (verbatim) | inline clamp `DETAILS_INLINE_MAX_CHARS` = 20000 (bd `wsao.8`) |
| `form_metadata.details` (booklet) | **NO** | YES | the reference floor; ~9.5k chars on W-7 |
| `form_metadata.booklet_text` | **NO** | YES | same |
| `spoken_name_translations` | no (resolved first) | no | the resolved string ships, never the map |
| `label_translations` | no (resolved first) | no | same |
| `pdf_field_name`, `pdf_position`, `pdf_on_value` | no | no | PDF mechanics, both surfaces |
| `_review` | no | no | authoring metadata |
| `_ignored_fields` | no | no | parked fields; never built as live fields |
| `hidden` / `read_only` | **see gap below** | listed w/ `shown` | |

## Measured on W-7 (2026-08-01)

- Form-level booklet: 9,487 chars. Present in secretary catalog, **absent from
  all 53 per-field voice blocks**.
- Secretary static catalog: ~142.6k chars (~35.7k tokens) -- the cacheable prefix.
- Largest single voice block: `reason` at 6,968 chars (~1.7k tokens), well under
  the 20k inline clamp, so nothing ships truncated. (Point-in-time snapshot --
  drifts a little with kit-content edits.)
- Voice per-field vs secretary whole-form ratio: ~20x smaller worst-case (the
  pinning test only requires >4x, as a regression floor, not the measured
  ratio).

## Known gap (bd `polyglot-pdf-52qm.7`)

`hidden` and `read_only` are **dropped** by `build_fields_from_schema`, so:

- a statically hidden field still produces a full voice-guidance block, and
- it accepts a voice write (no read-only guard in validation).

On W-7 that is the 7 `agent_*` Acceptance-Agent fields. Pinned by
`backend/tests/unit/test_52qm7_static_field_states.py` as characterization tests
(they assert the CURRENT behavior and say what to flip when fixed).

`SchemaFormStateManager.getProgress` filters its denominator correctly (fixed in
bd `polyglot-pdf-jtbg`, 2026-08-04) -- it no longer counts statically hidden
fields. `VoiceOverlay.tsx`'s 3 progress-counter sites were migrated onto the
shared `getProgressCounts` helper (bd `polyglot-pdf-kbkd`); `VoiceOverlayMobile.tsx`'s
one `schema.fields.length` site is deliberately unmigrated -- it renders a
static "N fields, M required" whole-form inventory, not a completion ratio, so
the raw total is the correct count there. The backend's own unfiltered
`Progress: N/M` render in `ai_context.py` remains a separate, still-open gap.
Pinned by `frontend/src/schema-forms/state/hiddenFieldCounting.test.ts`, which
drives the real `getProgress`/`getProgressCounts` as a regression guard and
documents the remaining unfixed surface in its header comment.

## Logging a rejected field id

A key the model sent is **not** guaranteed to be a schema id -- on an arg swap it
can carry the user's answer (Codex PR #264 P0). `validation_failures` therefore
echoes a rejected key only when it resolves against the session's full id space
(`FormFillingService._is_known_field_id`: schema + merged + manifest) and reduces
anything else to `<unrecognized:N chars>`. The predicate must be session-wide,
not the active validation pool -- a pool-scoped check would redact the real
sibling id the logging exists to surface.

## Adding a key

1. Decide the row above and add it.
2. If it is form-level or booklet-sized, it belongs to the **secretary only**.
3. Extend the boundary test so the new key is asserted on both surfaces.
