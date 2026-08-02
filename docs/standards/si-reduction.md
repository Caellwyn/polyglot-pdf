# System-instruction (SI) reduction -- frozen contract

**Tracks:** backend/config.py backend/services/ai_context.py backend/services/manifest_service.py

*Last updated: 2026-08-02 (bd polyglot-pdf-6bq8: the per-field guidance render's `Options:` segment now carries the option COUNT plus a per-turn recital imperative -- `Options (N -- read ALL N aloud when asking; the user cannot see them): [...]`, switching above `ai_context.LONG_OPTION_LIST_THRESHOLD` (20) to a `long standard list` marker that the DTI SI's new `PRESENTING OPTIONS` block resolves to ask-directly-and-offer-the-full-read-out (the 50-state selects). The static DTI SI gained the `PRESENTING OPTIONS` block (full recital, no summarizing, no one-by-one yes/no walk) and WORKFLOW step 1 wires the recital into the ask step; both initiating templates direct "read EVERY option aloud", and the RESUME template's "one short sentence" is now scoped to option-less fields -- unqualified, it overrode the recital live. The SI remains fully static.) Prior: 2026-07-26 (bd polyglot-pdf-wsao.8: the `Official reference text:` segment is clamped to the 20k-char inline budget at render (`guidance_contract.clamp_details_inline` -- paragraph-boundary cut + a topic index of what the secretary additionally holds); the static SI gained the INFORMATION-NEVER-ADVICE rule and the DEEP QUESTIONS rule now names `ask_secretary` actionably; the compression-window derivation adds `injection_budget_tokens` (the largest clamped per-field details, computed by `FormFillingService` from the schema) so a details-bearing initiating message cannot 1007 at session assemble. SI remains fully static.) Prior: 2026-07-25 (bd polyglot-pdf-wsao.1: the per-field guidance render may now carry an `Official reference text:` segment -- verbatim official-booklet excerpts from `help.details`, injected inline for the CURRENT field only (sprint-16 decoupled storage/delivery, v1 inline policy). The static DTI SI gained one behavioral line (`DEEP QUESTIONS:`) directing the model to ground requirement answers in that reference text and to ask the secretary when it holds none -- the SI remains fully static/byte-identical across forms. The spoken ask-hint (`formatNextFieldHint`) still appends ONLY `help.instructions`, never `help.details`.) Prior: 2026-07-17 (bd polyglot-pdf-ow1e: guidance option labels now render pre-translated into the session language via the runtime option-translation overrides -- see the per-field-guidance bullet and [../journal/entries/2026-07-17-bd-ow1e-runtime-option-label-translation.md](../journal/entries/2026-07-17-bd-ow1e-runtime-option-label-translation.md)). Prior: 2026-07-12. Continuous-DTI is the production default (`USE_DTI` defaults true, bd polyglot-pdf-7872); the legacy full-SI is the deprecated section-reset fallback (bd polyglot-pdf-55jg). The JIT manifest SI mode was removed (bd polyglot-pdf-en2j); the two surviving SI modes are DTI (shipped) and legacy full-SI (fallback). Both templates' CONSTRAINTS direct the model to briefly convey a field's Note / hint-carried context WHILE asking (bd polyglot-pdf-bo4m; the qualifying fine print was rendered but not voiced); the per-turn `{next_field_hint}` string built by the frontend (`formatNextFieldHint`) appends `help.instructions` as "Context to briefly convey when asking: ...". See [../journal/entries/2026-07-05-bd-bo4m-field-fine-print-reaches-voice-ai.md](../journal/entries/2026-07-05-bd-bo4m-field-fine-print-reaches-voice-ai.md). The legacy SI renders the canonical nested `help` block (`help.instructions`/`help.format_hint`) (bd polyglot-pdf-jnjj.23). Created as the F1 foundation contract (bd polyglot-pdf-jnjj.2).*

This is the interface the SI templates and their placeholder sets build against, so
work touching the system instruction does not collide on the `config.py` templates.
It pins: the SI template shapes, the surviving placeholder set, and the ownership of
the ADDRESS-CONSISTENCY removal. The cost rationale (why the SI is the lever -- the
measured "text-in is 95-98% of 2.5 cost, and it's the per-turn SI" invariant) lives
in [logging-and-cost.md](logging-and-cost.md) (MANDATORY read before SI/cost work);
the model-selection rule lives in [ai-models.md](ai-models.md); this doc owns the
**SI shape** contract.

## Current state: two SI modes, one builder

`backend/services/ai_context.py::build_form_context()` builds the SI on every
(re)connect (the backend is stateless -- it rebuilds from the WS handshake each
time) and branches on the `USE_DTI` flag (`backend/config.py`, **default
`true`** -- continuous-DTI is the production law of the land, bd
polyglot-pdf-7872; set `USE_DTI=false` for the deprecated legacy fallback):

| Mode | Template (`config.py`) | The cost driver |
|------|------------------------|-----------------|
| **DTI** (`USE_DTI=true`, the default/shipped mode) | `DTI_SYSTEM_INSTRUCTION` | Nothing form-specific. The SI is a FULLY STATIC behavioral backbone with NO field data and NO form/session state (byte-identical across every form/section). The CURRENT field's guidance rides the initiating message; each next field's guidance rides the `confirm_field` tool response. See "DTI: guidance injection" below. |
| **Legacy** (`USE_DTI=false`, deprecated fallback) | `SYSTEM_INSTRUCTION` | `{fields_json}` -- the CURRENT SECTION's fields dumped as text. The legacy handshake builder sends `extractSectionFields(currentSectionId)` as `schema`, so the dump is the active section, NOT the whole form. Each field's line carries its authored guidance: the canonical nested `help.instructions` -> `Note:` and `help.format_hint` -> `Format:` (flat `description`/`format` as fallback; bd polyglot-pdf-jnjj.23). |

> **The legacy SI is per-section, not whole-form** -- and it belongs to the
> DEPRECATED section-reset fallback (bd polyglot-pdf-55jg; see
> [section-reset-deprecation.md](section-reset-deprecation.md)). In that flow the
> live model only ever sees the current section's fields, because each section switch
> restarts the Live session with a fresh section SI. The DTI default carries the whole
> form as one session; cross-section recall comes from the exploration tools
> (`ask_secretary`), not from carrying other sections in the SI.

`build_form_context()` selects exactly one template per build: `DTI_SYSTEM_INSTRUCTION`
when `USE_DTI` is set (returned byte-identically, no `.format(...)` -- it carries no
placeholders), else `SYSTEM_INSTRUCTION.format(...)` with the placeholder set below.

## DTI: guidance injection (the shipped path)

DTI (Dynamic Turn Injection, bd polyglot-pdf-jnjj.22; epic polyglot-pdf-13w7) moves
everything form-specific OFF the SI and onto the per-turn injection:

- **Per-field guidance** -- `render_field_guidance` (`ai_context.py`) renders one
  field's guidance (from `manifest_service.get_field_guidance`, incl. `fill_language`).
  Option labels render pre-translated into the session language when the runtime
  option-translation overrides are available (bd polyglot-pdf-ow1e:
  `option_label_overrides` substitutes the label and omits `spoken_label` on
  overridden options; option VALUES stay English for tool-call matching, and the
  DTI SI's MATCHING block scopes its translate-aloud rule to the English-fallback
  window). No overrides -> byte-identical English render.
  When the field carries `help.details` (verbatim official-booklet excerpts, bd
  polyglot-pdf-wsao.1), the render appends an `Official reference text:` segment --
  inline v1 delivery per the sprint-16 plan; a no-details render is byte-identical
  to the pre-wsao.1 output. The spoken ask-hint path (`formatNextFieldHint` ->
  `strip_field_id_from_hint`) carries only `help.instructions`, never details.
  The SAME text delivers field 1 via the initiating message
  (`FormFillingService.send_initiating_message`) and fields 2..N via the `confirm_field`
  tool response (`response["next_field_guidance"]`), so the model sees identical
  guidance whichever path delivers it. The next field's guidance is CLIENT-SUPPLIED on
  the `next_field_hint_response` and rendered into the `confirm_field` response by
  `callback_handler.py`, honoring the stateless / client-owns-state invariant.
- **Form/section metadata** -- `render_section_metadata` (`ai_context.py`) renders the
  form title, section n/total, label, previous spoken names, and confirmation policy
  onto the initiating message at session/section start (bd polyglot-pdf-uogm). The
  static DTI SI carries none of it.

DTI is carried over the **manifest-first handshake transport** (`handshake_jit` WS
message type, `schema["jit_mode"]`, the `jit_mode_enabled` session-ready signal
`= settings.USE_DTI`, and the frontend's `jitModeEnabled` state). That transport
survived the JIT-mode purge (bd polyglot-pdf-en2j) as DTI's carrier -- it is documented
in [../components/websocket-routing.md](../components/websocket-routing.md) and
[../components/schema-forms.md](../components/schema-forms.md).

## Placeholder set (the legacy full-SI interface)

The DTI template carries NO placeholders (it is static). The legacy `SYSTEM_INSTRUCTION`
template is the only one `build_form_context()` calls `.format(...)` on; its placeholder
set is:

`{form_title}`, `{section_number}`, `{total_sections}`, `{section_label}`,
`{section_list}`, `{filled_count}`, `{total_fields}`, `{unfilled_count}`,
`{fill_language}`, `{previous_spoken_names}`, `{next_field_hint}`,
`{confirmation_policy}`, and `{fields_json}` (the full current-section field dump).

> **`fields_json` is a placeholder NAME, not JSON.** It carries pipe-separated field
> text (the comment at `config.py` notes this -- kept for compatibility). Do not "fix"
> it to JSON.

## ADDRESS CONSISTENCY prose: deleted, owned by B

Both SI templates carry an `ADDRESS CONSISTENCY:` block instructing the LIVE model to
cross-check address fields (zip-vs-state, etc.) itself. This is the
contradiction-checking the epic DELEGATES to the cheap validator.

- **The removal is owned by bead B1 (polyglot-pdf-jnjj.13)**, and is HARD-GATED on the
  validator being live: B1 depends on B2-B5 closed + the G1 detection gate passing, so
  the in-SI check is never removed until the flash-lite validator replaces it (no window
  with zero contradiction detection).
- The verdict/payload/steering shapes the validator uses are owned by the
  validation-delegation standard (F3, bd polyglot-pdf-jnjj.4), not here.

## What changes this contract

Any edit that adds/removes a legacy placeholder, changes the DTI guidance-injection
shape, or moves the ADDRESS-CONSISTENCY ownership updates THIS doc first (current-state
only -- the journal holds the history), then the code.
