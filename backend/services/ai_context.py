from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
from backend.config import get_settings
from backend.services.manifest_service import get_field_guidance

# A select/dropdown -- e.g. the 50-state lists, height feet/inches -- always
# renders the ask-directly marker instead of the forced recital, regardless of
# count (maintainer directive 2026-08-02, bd polyglot-pdf-s503). The gate names
# the ASK-DIRECTLY side, not the recital side (bd polyglot-pdf-cqx6): an
# option-bearing field with an unrecognized/absent type (nothing forbids
# options on a text field, and LLM extraction has invented odd types) must
# degrade TOWARD reciting the choices aloud -- the accessibility-safe
# direction -- never silently away from it.
ASK_DIRECTLY_OPTION_TYPES = {"select"}

# Above this many options, even a radio/checkbox group's guidance switches to
# the "long standard list" marker and the DTI SI's PRESENTING OPTIONS rule has
# the model ask directly + offer the full read-out instead of an unconditional
# recital (bd polyglot-pdf-6bq8). Chosen so every substantive choice list in
# the current kits (W-7 reason: 8; I-90 Part 2 reason: 12) is read in full;
# maintainer-reviewed as reasonable for now, may be tuned later.
LONG_OPTION_LIST_THRESHOLD = 20

# The two-option natural-question marker (bd polyglot-pdf-41fi) asserts that ONE
# question can carry BOTH choices. That claim is only true for a SINGLE-select
# field: on a multi-select the user may legitimately want BOTH options, and an
# exclusive-choice ask ("is it this or that?") forecloses that (bd
# polyglot-pdf-9tuu). Named on the MULTI-select side, mirroring the
# ASK_DIRECTLY_OPTION_TYPES rationale above: a field whose type is unrecognized
# or absent is NOT assumed multi-select, so it keeps the natural-question ask
# rather than degrading to a two-item list recital.
#
# "checkbox" is in the set, but ONLY reaches this gate when it carries options
# -- which is exactly the legacy v1 group idiom, a genuine multi-select. Three
# independent places agree: schema_repair._membership_trigger treats it as
# selecting FROM A SET ("v1 group modeling: type checkbox with options"), its
# _normalize_checkbox_shapes RETYPES a checkbox with >= 2 options to
# checkbox_group, validation.ts's isCheckboxGroupField treats it as a group, and
# FieldRenderer routes it to the same CheckboxField that branches on
# `!field.options` to render the check-as-many-as-you-like group UI.
# A v2 standalone checkbox has NO options and so never reaches the options
# branch at all -- its value is a boolean.
# Without this, a kit that skipped repair (hand-authored, editor-drafted, or a
# pre-repair draft) with two such options got the exclusive-choice ask over a UI
# where both boxes are checkable (2nd Opus outer review, final round).
MULTI_SELECT_OPTION_TYPES = {
    "checkbox_group", "checkbox", "multiselect", "multi_select",
}

# The same marker also assumes both labels are short enough to fold into one
# natural question. Two shipped-kit pairs are not (bd polyglot-pdf-575i): I-90
# 'p7_checkbox7' carries ~23- and ~27-word legal declarations whose
# representation-scope clause a single question drops outright. Above this word
# count the pair falls back to the normal recital, so the full substance of both
# options is still read aloud.
#
# 20 sits in the gap this corpus actually shows. Measured over every 2-option
# field in the three shipped kits, the longest label of each pair runs
# 1,1,1,1,1,2,2,2,3,3,4,5,6 words for the plainly-either/or fields, then 17 for W-7
# 'previously_received_itin_or_irsn' -- a genuine yes/no whose labels are padded
# with the printed-form navigation the SI already tells the model not to speak
# ("Yes. Complete line 6f. ...") -- and then 27 for the I-90 declaration. The
# threshold must sit above the W-7 case (it IS one natural question) and below
# the I-90 one; 20 sits inside that 17-to-27 gap with room on both sides,
# deliberately nearer the low end so a slightly wordier genuine either/or
# still asks naturally.
#
# Those counts are ENGLISH, and the render measures the English label even in a
# translated session (see the positional read in render_field_guidance). Word
# count is not translation-invariant, so a threshold calibrated on English MUST
# be applied to English or the branch becomes language-dependent -- which it
# briefly was, flipping BOTH of the fields above on shipped kits (Opus outer
# review, this PR).
TWO_OPTION_MAX_LABEL_WORDS = 20


def render_field_guidance(
    field: Optional[Dict[str, Any]], fill_language: Optional[str] = None,
    spoken_language: Optional[str] = None,
    option_label_overrides: Optional[Dict[str, str]] = None,
    spoken_name_overrides: Optional[Dict[str, str]] = None,
) -> str:
    """Render a single field's guidance as the readable text block the model reads
    (bd polyglot-pdf-jnjj.22, Dynamic Turn Injection).

    Single source of truth for the INJECTION path: this same text delivers field 1
    via the initiating message (FormFillingService.send_initiating_message) and
    fields 2..N via the confirm_field tool response, so the model sees identical
    guidance whichever path delivers it. The DTI system instruction itself is fully
    static and carries NO field guidance (epic polyglot-pdf-13w7, beads
    polyglot-pdf-1ac3 + polyglot-pdf-j748). Accepts a raw field dict (full schema)
    and reduces it via manifest_service.get_field_guidance.

    fill_language (bd polyglot-pdf-uogm): when set, appends a "Fill language: <lang>"
    segment so the language for field VALUES rides with EVERY field render -- the
    static DTI SI no longer carries it. Omitted/None -> no segment (legacy/JIT and
    the no-arg callers render byte-identically).

    spoken_language (bd polyglot-pdf-ghv4): when set, appends a "Speak <lang>
    aloud" segment so the SPOKEN-language rule is re-asserted on every injected
    guidance block -- long Spanish sessions drifted into English because the only
    spoken-language anchor was the session-start message. Omitted/None -> no
    segment (the initiating-message path already carries "Speak {spoken_language}"
    in its template and passes None here).

    option_label_overrides (bd polyglot-pdf-ow1e): when set, option labels are
    substituted with their session-language translations (spoken_label omitted
    on overridden options; values untouched) so the rendered Options list is
    already in the language the model speaks. Omitted/None/empty -> the render
    is byte-identical to before.

    spoken_name_overrides (bd polyglot-pdf-tupu.2): when set, the Spoken: line
    carries the field name in the session language (the field-level analog of
    the option-label override). Omitted/None/miss -> English, byte-identical.
    """
    guidance = (
        get_field_guidance(field, option_label_overrides=option_label_overrides,
                           spoken_name_overrides=spoken_name_overrides)
        if field else None
    )
    if not guidance:
        return "No fields available"

    # Unwrap a (str, Enum) FieldType member ONCE, for BOTH the model-visible
    # Type: line and the options gate below -- str(FieldType.RADIO) is
    # 'FieldType.RADIO', not 'radio' (bd polyglot-pdf-285t; the Type: line was
    # the missed half, Opus outer review on this PR).
    _t = guidance.get("type")
    _type_value = getattr(_t, "value", _t)
    parts = [
        f"ID: {guidance['field_id']}",
        f"Spoken: {guidance['spoken_name']}",
        f"Type: {_type_value if _type_value is not None else 'text'}",
    ]
    if guidance.get("required"):
        parts.append("Required: true")
    if guidance.get("instructions"):
        parts.append(f"Instructions: {guidance['instructions']}")
    if guidance.get("format_hint"):
        parts.append(f"Format: {guidance['format_hint']}")

    options = guidance.get("options")
    if options:
        opt_strs = []
        # The label the LENGTH rule measures, undecorated and always ENGLISH.
        #
        # Two things would corrupt this measurement if taken naively:
        #  - opt_strs carries the '"label" (use value: v)' wrapper, which is
        #    machine plumbing the model never says aloud;
        #  - by the time options reach here they may already be TRANSLATED
        #    (manifest_service._apply_label_overrides substitutes the session
        #    language into opt['label']). Word count is not translation-
        #    invariant, so measuring the translated text made the two-option
        #    branch language-dependent: measured live, I-90 'p7_checkbox7' fell
        #    back UNDER the threshold in Chinese and Korean (re-introducing the
        #    exact substance drop bd polyglot-pdf-575i fixed) while W-7
        #    'previously_received_itin_or_irsn' rose OVER it in 8 of 17 baked
        #    languages (re-introducing the bd 41fi recital). The gate must
        #    describe the FIELD, not the session, so it measures English.
        #
        # The English label is read POSITIONALLY from the raw `field` rather
        # than recovered from the override map. get_field_guidance builds its
        # options from field["options"] through _sanitize_options and
        # _apply_label_overrides, both plain list comprehensions -- so the two
        # lists are 1:1 by index, and index i's pre-override label IS the
        # English one. Exact, and it needs no map at all.
        #
        # A reverse lookup over option_label_overrides (keyed by English label)
        # was the earlier approach and is NOT equivalent: it keys on the
        # TRANSLATED string but fires on whatever sits in opt["label"], and
        # those are different populations. An option the secretary did not
        # translate stays English, and a single unrelated long label mapping TO
        # that same string re-attributed its word count -- e.g. a 2-option
        # "Yes"/"No" field silently measured 25 words when some other label
        # translated to "Yes". Reachable on a partially-baked kit, since
        # build_translation_overrides records only what the secretary returned
        # (2nd independent Opus outer review).
        # Source the raw options EXACTLY as get_field_guidance does
        # (manifest_service.py: `field.get("options") or field.get("allowed_values")`)
        # -- an `allowed_values`-shaped field is a supported read-side shape, and
        # reading only "options" left raw_options None for it, so the fallback
        # measured the TRANSLATED label and the branch went language-dependent
        # again on exactly that shape (both final Opus outer reviews, found
        # independently). If the two sourcing rules ever diverge the length guard
        # below degrades to the fallback rather than mis-indexing.
        raw_options = None
        if isinstance(field, dict):
            raw_options = field.get("options") or field.get("allowed_values")
        if not isinstance(raw_options, list) or len(raw_options) != len(options):
            raw_options = None

        def _english_label(index, fallback):
            # Fallback = the possibly-translated label, used only when the raw
            # options are absent or mis-shaped (a caller passing pre-reduced
            # guidance). Same behavior as before any override existed.
            if raw_options is None:
                return fallback
            raw = raw_options[index]
            if isinstance(raw, dict):
                return raw.get("label") or raw.get("value") or fallback
            return raw if isinstance(raw, str) else fallback

        measured_labels = []
        for index, opt in enumerate(options):
            if isinstance(opt, dict):
                opt_value = opt.get("value", "")
                opt_label = opt.get("label", "")
                if opt_label and opt_value and opt_label != opt_value:
                    opt_strs.append(f'"{opt_label}" (use value: {opt_value})')
                elif opt_label:
                    opt_strs.append(opt_label)
                else:
                    opt_strs.append(opt_value)
                spoken = opt_label or opt_value or ""
            else:
                opt_strs.append(str(opt))
                spoken = str(opt)
            measured = _english_label(index, spoken)
            # str() so a malformed kit (an LLM-extracted/editor-drafted label
            # that is a number or None) cannot crash the render on .split();
            # schema_lint does not assert the label is a string, and every
            # render call site is unguarded.
            measured_labels.append(
                measured if isinstance(measured, str) else str(measured)
            )
        n = len(opt_strs)
        # The user cannot read the form, so the model's recital is their only
        # access to the choices (bd polyglot-pdf-6bq8). The count + imperative
        # ride the injection so the directive is in the LATEST guidance block on
        # exactly the turns that need it; the full behavioral rule (and the
        # standard-list carve-out these markers trigger) is the DTI SI's
        # PRESENTING OPTIONS block. Recital is TYPE-scoped (bd polyglot-pdf-s503
        # + cqx6): a select always asks directly; every OTHER option-bearing
        # type (incl. an unrecognized or absent one) falls to the recital side.
        ftype = str(_type_value or "").lower()
        if ftype in ASK_DIRECTLY_OPTION_TYPES:
            parts.append(
                f"Options ({n} -- standard list; ask directly and offer to "
                f"read all {n} aloud): [{', '.join(opt_strs)}]"
            )
        elif n > LONG_OPTION_LIST_THRESHOLD:
            parts.append(
                f"Options ({n} total -- long standard list; ask directly and "
                f"offer to read all {n} aloud): [{', '.join(opt_strs)}]"
            )
        elif n == 2 and ftype not in MULTI_SELECT_OPTION_TYPES and all(
            len(label.split()) <= TWO_OPTION_MAX_LABEL_WORDS
            for label in measured_labels
        ):
            # A two-option field IS one natural question (bd polyglot-pdf-41fi):
            # forcing the list recital produced "Select No, Select Yes -- which
            # one applies?" on yes/no fields. The SI's two-option rule carries
            # the phrasing detail (yes/no vs either/or).
            #
            # Two carve-outs, because the marker asserts an EXCLUSIVE choice
            # between two SHORT labels and neither holds universally:
            #  - a MULTI-select at n==2 (bd polyglot-pdf-9tuu) -- the user may
            #    want both, so it falls to the recital, whose SI rule already
            #    says "or which ones, for a multi-select";
            #  - a pair whose labels are too long to fold into one question
            #    (bd polyglot-pdf-575i) -- reciting both is the only way the
            #    user hears their full substance.
            parts.append(
                f"Options (2 -- ask ONE natural question that makes both "
                f"choices clear; do not recite the labels as a list): "
                f"[{', '.join(opt_strs)}]"
            )
        else:
            parts.append(
                f"Options ({n} -- read ALL {n} aloud when asking; the user "
                f"cannot see them): [{', '.join(opt_strs)}]"
            )

    validation = guidance.get("validation")
    if isinstance(validation, dict):
        for key in ("format", "format_preset", "pattern", "min", "max",
                    "min_length", "max_length", "minLength", "maxLength"):
            if key in validation:
                parts.append(f"{key}: {validation[key]}")
    if guidance.get("example"):
        parts.append(f"Example: {guidance['example']}")
    # Official reference text (bd wsao.1): verbatim booklet excerpts for THIS
    # field, injected inline so deep questions are answered from source while
    # the field is current (v1 delivery, sprint-16 plan). Appended near the end
    # so a no-details render stays byte-identical; behavioral rules (ground
    # claims here, never read aloud wholesale) live in the static SI.
    if guidance.get("details"):
        parts.append(f"Official reference text: {guidance['details']}")

    # fill_language rides with every field render (bd polyglot-pdf-uogm): the
    # language for field VALUES, distinct from the spoken language. Appended last
    # so a no-arg / non-DTI render is byte-identical.
    if fill_language:
        parts.append(f"Fill language: {fill_language}")
    # spoken_language re-anchors the conversation language per injection
    # (bd polyglot-pdf-ghv4); distinct from fill_language above. UNMISTAKABLY is
    # Google's documented power phrasing for language adherence
    # (docs/genai_docs/live-api-best-practices.md; bd polyglot-pdf-oqkj).
    if spoken_language:
        parts.append(
            f"Speak {spoken_language} aloud -- respond UNMISTAKABLY in {spoken_language}"
        )

    return " | ".join(parts)


def render_section_metadata(
    form_title: Optional[str] = None,
    section_number: Optional[int] = None,
    total_sections: Optional[int] = None,
    section_label: Optional[str] = None,
    previous_spoken_names: Optional[List[str]] = None,
    confirmation_policy: Optional[str] = None,
    section_label_overrides: Optional[Dict[str, str]] = None,
    spoken_name_overrides: Optional[Dict[str, str]] = None,
) -> str:
    """Render the form/section metadata block carried by the DTI initiating message
    (bd polyglot-pdf-uogm). The static DTI SI no longer carries form/session state,
    so this block delivers it via the injection at session start AND section start.

    IMPORTANT (bd polyglot-pdf-fu1h, F1): callers MUST source these values from the
    section_metadata the service holds (FormFillingService._last_section_metadata)
    /the switch payload carries -- NOT from schema["manifest"], which is ABSENT on a
    section-switch handshake (extractSectionFields sends full fields, no manifest),
    so a manifest-sourced block would be empty on sections 2..N.

    Each line is omitted when its inputs are absent, so single-section forms and the
    first-section (no prior switch) case degrade cleanly. When confirmation_policy is
    not supplied but section_number+total_sections are, it is derived via
    get_confirmation_policy. Returns "" if nothing renders.
    """
    lines: List[str] = []

    # The title/section line renders only when there is SUBSTANTIVE position info
    # (a section number, a section label) or a real form title -- NOT a bare "Form"
    # fallback alone, which would be meaningless noise. This is what lets the
    # "nothing to render -> return ''" guard below actually fire (so the caller's
    # `if block:` skip works on a metadata-less session) rather than always emitting
    # a useless "FORM CONTEXT:\nForm" line (fresh-eyes finding on this PR).
    # Session-language section label (bd tupu.2 -- closes the zmlo residual
    # where a greeting read a section title in English). Miss -> English.
    if section_label and section_label_overrides:
        section_label = section_label_overrides.get(section_label) or section_label
    has_position = section_number is not None and total_sections is not None
    if has_position or section_label or form_title:
        title = form_title or "Form"
        if has_position and section_label:
            lines.append(f"{title} | Section {section_number} of {total_sections}: {section_label}")
        elif has_position:
            lines.append(f"{title} | Section {section_number} of {total_sections}")
        elif section_label:
            lines.append(f"{title} | {section_label}")
        else:
            lines.append(title)

    if previous_spoken_names:
        # Session-language names (bd tupu.2); miss -> English, same fallback
        # as every other override consumer.
        if spoken_name_overrides:
            previous_spoken_names = [
                spoken_name_overrides.get(n) or n
                for n in previous_spoken_names
            ]
        # These names are given to you HERE -- do not fetch them from the
        # secretary (bd polyglot-pdf-2af7). The current field's own id + spoken
        # name are always in the latest guidance block too; ask_secretary is for
        # recalling the user's past ANSWERS/values, never field metadata you
        # already hold.
        lines.append(
            "Fields already completed (their exact spoken names are listed here; "
            "use ask_secretary to recall the user's ANSWERS to them, not their "
            "names): " + ", ".join(previous_spoken_names)
        )

    policy = confirmation_policy
    if policy is None and has_position:
        policy = get_confirmation_policy(section_number, total_sections)
    if policy:
        lines.append(f"End-of-section confirmation: {policy}")

    if not lines:
        return ""
    return "FORM CONTEXT:\n" + "\n".join(lines)


# Shared additive-confirmation preamble (bd polyglot-pdf-choa): makes explicit
# that the end-of-{scope} review is ADDITIONAL to -- never a replacement for --
# the per-field confirm loop, so the model can't read "read all fields back at
# the end" as permission to batch/skip per-field confirmation (the first field
# of a section was auto-confirmed without its read-back under the old wording).
# It deliberately REFERENCES the per-field step without restating it: spelling
# the read-back out again makes Gemini double-read every field (bd
# polyglot-pdf-yn6q). ONE constant, used by both get_confirmation_policy and
# the non-sectioned default in build_form_context, so the wording cannot drift.
_CONFIRMATION_ADDITIVE_PREAMBLE = (
    "This end-of-{scope} review is IN ADDITION to confirming each field "
    "one-by-one as you go (every field, including the first, gets its own "
    "read-back and confirmation). "
)


def get_confirmation_policy(section_number: int, total_sections: int) -> str:
    """Generate confirmation policy text based on section number.
    
    Args:
        section_number: Current section (1-indexed)
        total_sections: Total number of sections in form
        
    Returns:
        Confirmation policy text for system instruction
    """
    # NOTE: there is no complete_section tool -- section completion is auto-
    # detected by the frontend once all fields in a section are confirmed. The
    # model's job is to confirm each field (confirm_field); it must NOT be told
    # to call complete_section.
    addition = _CONFIRMATION_ADDITIVE_PREAMBLE.format(scope="section")
    if section_number <= 2:
        # First two sections: Full graduated end-of-section confirmation.
        # This block fires only when ALL fields in the section are confirmed.
        return addition + (
            "When ALL fields in this section are confirmed: "
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'Is everything correct?'"
        )
    elif section_number >= total_sections:
        # Last section: Extra careful final confirmation.
        return addition + (
            "When ALL fields in this section are confirmed: "
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'This is the last section - is everything correct?'"
        )
    else:
        # Middle sections: Simple end-of-section confirmation.
        return addition + (
            "When ALL fields in this section are confirmed: "
            "Say 'Section done. Ready for the next section?'"
        )


def build_form_context(
    schema: dict,
    current_values: dict,
    fill_language: str = "English",
    section_number: Optional[int] = None,
    total_sections: Optional[int] = None,
    section_label: Optional[str] = None,
    previous_spoken_names: Optional[List[str]] = None,
    next_field_hint: Optional[str] = None,
    is_reconnect: bool = False,
) -> str:
    """Build form context system instruction for AI.

    This system instruction provides the AI with complete form schema and current state.
    Uses Settings.SYSTEM_INSTRUCTION template for centralized configuration.

    Args:
        schema: Form schema with field definitions
        current_values: Current field values from client (may be pre-filled by user)
        fill_language: Language to use for filling form field values (default: English)
        section_number: Current section number (1-indexed), None for non-sectioned forms
        total_sections: Total number of sections, None for non-sectioned forms
        section_label: Human-readable section label (e.g., "Client Information")
        previous_spoken_names: List of spoken names from completed sections
    
    Returns:
        System instruction text
    """
    settings = get_settings()
    
    # Build field metadata with current values
    fields_info = []
    filled_count = 0
    
    for idx, field in enumerate(schema.get("fields", []), start=1):
        field_id = field.get("id")
        field_name = field.get("name")
        field_type = field.get("type", "text")
        # Required lives at validation.required (canonical shape; bd a1ql).
        required = bool((field.get("validation") or {}).get("required"))

        # Check if this field has a current value
        current = current_values.get(field_id, "")
        field_info = {
            "order": idx,
            "id": field_id,
            "name": field_name,
            "type": field_type,
            "required": required,
            "filled": bool(current)
        }
        
        if current:
            field_info["current_value"] = current
            filled_count += 1
        
        # Add allowed values if present
        allowed_values = field.get("allowed_values") or field.get("options")
        if allowed_values:
            field_info["allowed_values"] = allowed_values
        
        # Add validation constraints
        if "format" in field:
            field_info["format"] = field.get("format")
        if "pattern" in field:
            field_info["pattern"] = field.get("pattern")
        if "min" in field:
            field_info["min"] = field.get("min")
        if "max" in field:
            field_info["max"] = field.get("max")
        if "minLength" in field:
            field_info["min"] = field.get("minLength")  # Use "min" in display for consistency
        if "maxLength" in field:
            field_info["max"] = field.get("maxLength")  # Use "max" in display
        if "placeholder" in field:
            field_info["placeholder"] = field.get("placeholder")
        if "description" in field:
            field_info["description"] = field.get("description")

        # Nested canonical help block (bd polyglot-pdf-jnjj.23). The FormField model
        # carries field-level guidance under field["help"] (FieldHelp:
        # instructions/format_hint/...), and real form-kit schemas (e.g.
        # form-kits/i-90/schema.json) populate help.instructions on every field --
        # but this builder previously read only the FLAT "description" key, so the
        # voice model got NONE of that authored guidance on real forms. Read the
        # nested block here: help.instructions feeds the "Note:" line (preferred over
        # a flat description), help.format_hint feeds "Format:" when no flat format.
        _help = field.get("help")
        help_block = _help if isinstance(_help, dict) else None
        if help_block:
            if help_block.get("instructions"):
                field_info["description"] = help_block["instructions"]
            # Use `not field_info.get("format")`, NOT `"format" not in field_info`:
            # a field can carry a flat "format": null (present-but-null, e.g. after a
            # round-trip through the optional ValidationRules) -- the "in" guard would
            # see the key, suppress the nested hint, and the renderer would then skip
            # the null and emit NO Format: line, dropping the guidance on exactly the
            # nested-help schemas this fix targets (Codex PR #230 round 2).
            if help_block.get("format_hint") and not field_info.get("format"):
                field_info["format"] = help_block["format_hint"]

        fields_info.append(field_info)
    
    form_title = schema.get("form_metadata", {}).get("title", "Form")
    total_fields = len(schema.get("fields", []))
    unfilled_count = total_fields - filled_count
    
    # Format fields in a more natural way to avoid JSON quote confusion
    # Build a clear text representation instead of JSON to prevent Gemini from
    # seeing field IDs like "reason[]" and returning them as "\"reason[]\""
    fields_lines = []
    for field_info in fields_info:
        field_id = field_info.get("id", "")
        field_name = field_info.get("name", "")
        field_type = field_info.get("type", "text")
        required = field_info.get("required", False)
        filled = field_info.get("filled", False)
        
        # Build field description line by line
        # Format: Field N | ID: field_id | Name: field_name | ...
        # This makes it crystal clear which is the ID to use in tool calls
        line_parts = [
            f"Field {field_info.get('order', '?')}",
            f"ID: {field_id}",
            f"Name: {field_name}",
            f"Type: {field_type}",
            f"Required: {required}",
            f"Filled: {filled}"
        ]
        
        if filled and "current_value" in field_info:
            line_parts.append(f"Current: {field_info['current_value']}")
        
        if "allowed_values" in field_info and field_info["allowed_values"]:
            allowed = field_info["allowed_values"]
            # Options are now guaranteed to be FieldOption objects (normalized at model level)
            # For radio/select fields, we need to show BOTH the label (what user hears/sees)
            # AND the value (what to send in the tool call)
            allowed_strs = []
            for opt in allowed:
                if isinstance(opt, dict):
                    # Extract both value and label
                    opt_value = opt.get("value", "")
                    opt_label = opt.get("label", "")
                    # Show label first (user-facing), then value (for tool call)
                    if opt_label and opt_value and opt_label != opt_value:
                        allowed_strs.append(f'"{opt_label}" (use value: {opt_value})')
                    elif opt_label:
                        allowed_strs.append(opt_label)
                    elif opt_value:
                        allowed_strs.append(opt_value)
                    else:
                        allowed_strs.append(str(opt))
                else:
                    # Fallback for non-dict options
                    allowed_strs.append(str(opt))

            if len(allowed_strs) <= 5:
                # Show all options if 5 or fewer
                line_parts.append(f"Options: [{', '.join(allowed_strs)}]")
            else:
                # Show first 3 and count for longer lists
                line_parts.append(f"Options: [{', '.join(allowed_strs[:3])}, ... ({len(allowed_strs)} total)]")
        
        # Add validation constraints if present
        if "format" in field_info and field_info["format"]:
            line_parts.append(f"Format: {field_info['format']}")
        
        if "min" in field_info:
            line_parts.append(f"Min: {field_info['min']}")
        
        if "max" in field_info:
            line_parts.append(f"Max: {field_info['max']}")
        
        if "pattern" in field_info and field_info["pattern"]:
            line_parts.append(f"Pattern: {field_info['pattern']}")
        
        if "placeholder" in field_info and field_info["placeholder"]:
            line_parts.append(f"Example: {field_info['placeholder']}")
        
        if "description" in field_info and field_info["description"]:
            line_parts.append(f"Note: {field_info['description']}")
        
        fields_lines.append(" | ".join(line_parts))
    
    fields_text = "\n".join(fields_lines)

    # Build section list for navigation
    # Format: "1. Personal Information, 2. Employment History, 3. References"
    # This helps Gemini understand section names, order, and handle requests like "go to last section"
    section_list_text = ""
    if schema.get("sections"):
        # Multi-section form - list all sections (NOT parts)
        # This is critical: Gemini must see section order (1-16 for I-90), not part order (1-8)
        section_items = []
        for section in schema.get("sections", []):
            order = section.get("order", "?")
            label = section.get("label", f"Section {order}")
            section_items.append(f"{order}. {label}")
        section_list_text = ", ".join(section_items)
    elif schema.get("parts"):
        # Fallback: If no sections array, use parts
        section_items = []
        for part in schema.get("parts", []):
            order = part.get("order", "?")
            label = part.get("label", f"Part {order}")
            section_items.append(f"{order}. {label}")
        section_list_text = ", ".join(section_items)
    else:
        # Single section form
        section_list_text = f"1. {form_title}"

    # Prepare section-specific context
    # Default values for non-sectioned forms (backward compatibility)
    section_num_text = section_number if section_number is not None else "1"
    total_sections_text = total_sections if total_sections is not None else "1"
    section_label_text = section_label if section_label else form_title
    
    # Format previous spoken names for context (legacy per-section mode; no
    # recall tool is declared here, this is informational only).
    # The frontend maintains a spokenNameToFieldId map, so we need to give Gemini all available names
    if previous_spoken_names and len(previous_spoken_names) > 0:
        # Include ALL spoken names - informational context on fields already filled
        previous_names_text = (
            "Fields already filled in completed sections: " +
            ", ".join(previous_spoken_names)
        )
    else:
        previous_names_text = "None (this is the first section)"
    
    # Get confirmation policy based on section number
    if section_number is not None and total_sections is not None:
        confirmation_policy = get_confirmation_policy(section_number, total_sections)
    else:
        # Default policy for non-sectioned forms.
        # Per-field confirm is WORKFLOW step 3; this is end-of-form only
        # (bd polyglot-pdf-yn6q). Same additional-not-replacement clarifier as
        # get_confirmation_policy (bd polyglot-pdf-choa), via the shared constant.
        confirmation_policy = _CONFIRMATION_ADDITIVE_PREAMBLE.format(scope="form") + (
            "When ALL fields are confirmed: "
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'Is everything correct?'"
        )

    # DTI (Dynamic Turn Injection, bd polyglot-pdf-jnjj.22): the SI is FULLY STATIC
    # (epic polyglot-pdf-13w7; 1ac3 made the constant zero-placeholder, uogm moved
    # the last form/session values off it). It carries NO field data and NO
    # form/session state, so the DTI branch takes NO schema-derived computation and
    # returns the constant byte-identically across every form/section (criterion 2).
    # Everything the model needs rides the INJECTION:
    #   - the current field's guidance (incl. fill_language) -> the initiating
    #     message (field 1) + the confirm_field response (fields 2..N), via
    #     render_field_guidance (bd polyglot-pdf-j748 / uogm).
    #   - form/section metadata (title, section n/total, label, progress,
    #     previous names, confirmation policy) -> render_section_metadata on the
    #     initiating message at session/section start (bd polyglot-pdf-uogm).
    # SI-mode selection: DTI (thin static SI + per-field injection) when USE_DTI,
    # else the legacy full-SI dump. getattr-guard so a minimal settings stub (some
    # unit tests) without USE_DTI falls through to the legacy branch rather than
    # AttributeError-ing. The JIT manifest SI mode was removed (bd polyglot-pdf-en2j);
    # the manifest-first handshake transport (handshake_jit / schema["jit_mode"])
    # survives as DTI's carrier and is handled by the DTI static SI, which does not
    # read schema["fields"].
    #
    # ALSO route a jit_mode-shaped schema to the DTI static SI even when USE_DTI is
    # off (rollback safety, originally Codex PR #229): such a schema carries only the
    # synthesized first field in schema["fields"] + a names-only manifest, so the
    # legacy full-dump branch would describe ONE field and lose the section. This
    # bites the DTI->legacy rollback window -- a client with a stale persisted
    # jitModeEnabled sends one more handshake_jit before session_ready corrects it.
    # The manifest lacks the full field dicts needed to rebuild a rich legacy dump,
    # so the static DTI SI (section-agnostic, no one-field dump) is the correct
    # handler for a manifest-first schema regardless of the flag.
    if getattr(settings, "USE_DTI", False) or schema.get("jit_mode"):
        system_instruction = settings.DTI_SYSTEM_INSTRUCTION
    else:
        # Legacy mode: Use full schema with SYSTEM_INSTRUCTION template
        system_instruction = settings.SYSTEM_INSTRUCTION.format(
            form_title=form_title,
            section_number=section_num_text,
            total_sections=total_sections_text,
            section_label=section_label_text,
            section_list=section_list_text,
            filled_count=filled_count,
            total_fields=total_fields,
            unfilled_count=unfilled_count,
            fields_json=fields_text,  # Still using fields_json placeholder name for compatibility
            fill_language=fill_language,
            previous_spoken_names=previous_names_text,
            confirmation_policy=confirmation_policy,
            next_field_hint=next_field_hint or "the first unfilled field"
        )

    # On mid-section reconnects, override any greet directive so Gemini resumes
    # silently rather than re-introducing the form/section (bd polyglot-pdf-vmxx).
    if is_reconnect:
        system_instruction = (
            system_instruction
            + "\n\nRESUME: The user has reconnected mid-session. "
            "Do NOT greet them. Do NOT re-introduce the form or section. "
            "Simply ask for the next field as if continuing naturally."
        )

    return system_instruction
