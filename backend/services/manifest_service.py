"""
Field-guidance service for Dynamic Turn Injection (DTI).

Builds the per-field guidance block the DTI SI mode injects for each field
(get_field_guidance), plus the shared option-sanitizer (_sanitize_options) that
strips option dicts to the model-facing keys. The legacy JIT manifest helpers
(generate_part_manifest, get_next_field_schema, format_manifest_for_context,
should_include_schema_in_response, estimate_manifest_tokens) were removed with the
JIT SI mode in bd polyglot-pdf-en2j; DTI is the shipped reduced-SI mode.
"""

import structlog

_log = structlog.get_logger(__name__)

# The only option keys a voice/text model needs. The schema option dicts also
# carry PDF plumbing (pdf_field_name, pdf_on_value, per-option pdf_position -- bd
# polyglot-pdf-5f41) and label_translations, which are meaningless to the model,
# cost tokens in every tool response, and are PDF-internal detail that must not
# leak into a model-facing payload.
_MODEL_FACING_OPTION_KEYS = ("value", "label", "spoken_label")


def _sanitize_options(options: list | None) -> list | None:
    """Strip option dicts to the model-facing keys (value/label/spoken_label).

    Used by get_field_guidance (the DTI per-field guidance builder) so PDF
    plumbing (pdf_field_name/pdf_on_value/pdf_position) and label_translations
    never leak into a model-facing payload (bd polyglot-pdf-lj5v; the boundary was
    first established in bd polyglot-pdf-5f41). It was originally shared with the
    JIT get_next_field_schema path, removed with the JIT SI mode in bd
    polyglot-pdf-en2j.

    Bare-string options (allowed_values-style lists) pass through unchanged --
    every other option consumer guards the same way (ai_context isinstance
    checks), and the pre-sanitizer code never crashed on them.
    """
    if not options:
        return options
    return [
        opt if not isinstance(opt, dict)
        else {k: opt[k] for k in _MODEL_FACING_OPTION_KEYS if opt.get(k) is not None}
        for opt in options
    ]


def _apply_label_overrides(options: list, overrides: dict) -> list:
    """Substitute translated option labels (bd polyglot-pdf-ow1e).

    For each sanitized option dict whose label has an override, replace the
    label and OMIT spoken_label -- an English spoken_label alongside a
    translated label would reintroduce the mixed-language confusion. The value
    is untouched, so tool-call matching (update_form_fields) is unaffected.
    Bare-string options and no-override labels pass through unchanged.
    """
    result = []
    for opt in options:
        if not isinstance(opt, dict):
            result.append(opt)
            continue
        override = overrides.get(opt.get("label"))
        if not override or override == opt.get("label"):
            result.append(opt)
            continue
        new_opt = {k: v for k, v in opt.items() if k != "spoken_label"}
        new_opt["label"] = override
        result.append(new_opt)
    return result


def get_field_guidance(
    field: dict, option_label_overrides: dict | None = None,
    spoken_name_overrides: dict | None = None,
) -> dict | None:
    """Build the per-field guidance block for Dynamic Turn Injection (bd
    polyglot-pdf-jnjj.22).

    Reads the canonical NESTED `help` block (`help.instructions`,
    `help.format_hint`) that real form-kit schemas use
    (e.g. form-kits/i-90/schema.json: help.instructions on every field), with the
    flat keys (help_text, description) as a fallback so the demo schema still
    renders. This is the single
    source of truth for a field's guidance: it feeds both the DTI system
    instruction (field 1) and the confirm_field tool response (fields 2..N), so the
    model sees identical guidance whichever path delivers it.

    PII-free schema only -- never user values.

    Args:
        field: A full field dict from the schema.
        option_label_overrides: Optional {english_label: translated_label} map
            (bd polyglot-pdf-ow1e). Applied AFTER _sanitize_options: overridden
            options carry the translated label and no spoken_label; values are
            untouched. None/empty -> byte-identical output to the no-arg call.
        spoken_name_overrides: Optional {english_spoken_name: translated} map
            (bd polyglot-pdf-tupu.2). Substitutes the guidance's spoken_name
            (keyed by the SAME spoken_name-or-name fallback string the bake
            collects) so the model reads the field's name in the session
            language. None/empty/miss -> English, byte-identical.

    Returns:
        A guidance dict, or None if no field. Keys: field_id, spoken_name, name,
        type, required, instructions, format_hint, details, options, validation,
        example. Absent keys are omitted (not null) to keep the rendered block lean.
    """
    if not field or not field.get("id"):
        return None

    help_block = field.get("help") if isinstance(field.get("help"), dict) else {}

    # instructions: nested help.instructions (canonical) -> flat help_text/description.
    instructions = (
        help_block.get("instructions")
        or field.get("help_text")
        or field.get("description")
    )
    # format_hint: nested help.format_hint (canonical) -> flat format.
    format_hint = help_block.get("format_hint") or field.get("format")

    # Session-language spoken name (bd tupu.2): the override map keys on the
    # spoken_name-or-name string (the id fallback below was never collected by
    # the bake, so it correctly stays untranslated).
    spoken = field.get("spoken_name") or field.get("name") or field.get("id")
    if spoken_name_overrides:
        spoken = spoken_name_overrides.get(spoken) or spoken
    guidance: dict = {
        "field_id": field.get("id"),
        "spoken_name": spoken,
        "type": field.get("type", "text"),
    }
    if field.get("name"):
        guidance["name"] = field["name"]
    # Required lives at validation.required (the canonical shape shared by every
    # kit + the frontend isFieldRequired reader; bd polyglot-pdf-a1ql).
    required = (field.get("validation") or {}).get("required")
    if required:
        guidance["required"] = required
    if instructions:
        guidance["instructions"] = instructions
    if format_hint:
        guidance["format_hint"] = format_hint
    # details: verbatim official-booklet reference text (bd wsao.1). Injected
    # inline for the CURRENT field only (v1 delivery policy, sprint-16 plan);
    # the spoken ask-hint path never reads it.
    details = help_block.get("details")
    if details:
        guidance["details"] = details

    # Options for select/radio/checkbox (label/value pairs or bare values).
    # SANITIZE via the shared helper (bd polyglot-pdf-lj5v) to the
    # value/label/spoken_label boundary -- never leak pdf_field_name/pdf_on_value/
    # pdf_position/label_translations into a model-facing payload.
    options = field.get("options") or field.get("allowed_values")
    if options:
        sanitized = _sanitize_options(options)
        # Runtime option-label translation (bd polyglot-pdf-ow1e): substitute
        # the session-language labels AFTER sanitizing, so the override applies
        # to exactly the model-facing dicts.
        if option_label_overrides:
            sanitized = _apply_label_overrides(sanitized, option_label_overrides)
        guidance["options"] = sanitized

    # Validation hints that help the model guide the user (no internal-only keys).
    validation = field.get("validation")
    if isinstance(validation, dict):
        minimal_validation = {
            k: validation[k]
            for k in ("format", "format_preset", "pattern", "min", "max",
                      "min_length", "max_length", "minLength", "maxLength")
            if k in validation
        }
        if minimal_validation:
            guidance["validation"] = minimal_validation
    # Flat placeholder as a last-resort example.
    if field.get("placeholder"):
        guidance.setdefault("example", field["placeholder"])

    return guidance
