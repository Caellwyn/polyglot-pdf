"""Secretary context renderer -- the form info the cheap secretary model reads.

PRODUCTION module (bd polyglot-pdf-jnjj.45a). The secretary
(gemini-2.5-flash-lite) is a pure retrieval+reasoning specialist: it holds the
form's per-field context plus the client's current values and answers the
principal's prose queries. This module renders that context, ALGORITHMICALLY, from
the same inputs the secretary gets in production:

  - the form schema (the full form-kits/<form>/schema.json shape) -- the STATIC
    catalog (metadata that never changes within a session: ideal cache-prefix
    content), and
  - the client's current form state -- the DYNAMIC tail: a flat field_values map
    plus a SEPARATE shown_map (applicability).

Why shown_map is a separate input (not derived from value): the real frontend
tracks shown/hidden INDEPENDENTLY of whether a field has a value (conditional UI).
The value-vs-applicability query class ("have they answered X?" when X is hidden
vs. empty-but-applicable) is only measurable if the renderer can represent that
distinction. Deriving shown from "has a value" collapses it.

Format here is GROUPED BY SECTION (parts -> sections -> fields). Comparing
alternative formats is a deferred follow-up (bd polyglot-pdf-jnjj.37).

CACHING CONTRACT (bd polyglot-pdf-jnjj.45, maintainer 2026-06-27): the secretary
is the TEXT model -- every ask() resends the full SI + full context (no
server-side memory). Gemini's implicit cache (charged ~1/10 rate) fires ONLY if
the TOP of the context is byte-identical call-to-call. So render_static_catalog()
(value-free, session-invariant) is the byte-stable PREFIX (never mutated within a
session); render_values_tail() (current values + applicability) is the small,
fresh, APPEND-ONLY tail.

INCLUDE/EXCLUDE contract (from docs/standards/validation-delegation.md + the
secretary research plan):
  INCLUDE per field: id, spoken_name, name/label, type, options (radio/select),
    help.instructions (+ help.format_hint), help.details (verbatim booklet
    excerpts, bd wsao.1), section label, current value, shown.
  INCLUDE form-level (bd wsao.1, sprint-16 plan): metadata.details (form-level
    guidance -- eligibility/documents/where-to-apply) and metadata.booklet_text
    (the WHOLE official instructions booklet, verbatim) -- the secretary's
    reference FLOOR, so form-level and orphaned-passage questions are
    answerable and the "ask the secretary" fallback is never circular. Both are
    session-invariant and render at the END of the static catalog (cacheable
    prefix stays byte-stable).
  EXCLUDE: PDF mechanics (pdf_position, pdf_field_name, consolidated_widgets,
    is_comb), validation.pattern/regex, raw show_if/controls_fields logic.

PII: this module renders whatever values it is handed -- in production that is
PHI and must never be logged. Callers log field ids / counts / token sizes, never
the rendered text or values.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

# Keys excluded from the secretary's view (PDF mechanics + validation internals +
# raw conditional logic). The renderer reads only the allowed keys explicitly, so
# this list is documentation of intent rather than a filter -- but kept here so the
# exclusion is auditable.
EXCLUDED_KEYS = (
    "pdf_position", "pdf_field_name", "consolidated_widgets", "is_comb",
    "validation", "show_if", "hide_if", "controls_fields", "conditional_fields",
    "conditional_behavior", "conditional_logic", "copy_to", "copy_from",
    "question_number", "read_only", "multiline", "max_length", "placeholder",
)

EMPTY = "<empty>"


def _field_index(schema: dict) -> dict:
    """Map field_id -> full field object (the flat top-level `fields` array is the
    source of the full objects; sections reference fields by id)."""
    return {f["id"]: f for f in schema.get("fields", [])}


def _section_label_map(schema: dict) -> dict:
    """Map section id -> human label."""
    return {sec["id"]: sec.get("label", sec["id"]) for sec in schema.get("sections", [])}


def _ordered_groups(schema: dict) -> list:
    """Yield (part_label, section_label, [field_id, ...]) in form order.

    Grouping walks `sections[].fields` (id reference lists), NOT each field's
    own section_id: the section arrays are authoritative for ORDER and for
    ASSIGNMENT (some fields carry a section_id that is not present in sections[],
    e.g. 'Part 3 - Biographic Information' -- a known schema drift; the reference
    lists place every referenced field correctly regardless). Parts are matched to
    sections via parts[].section_ids; sections a part does not claim (part_7 has an
    empty section_ids in this schema) fall back to a best-effort part match by id
    prefix, else an 'Other' part.
    """
    sec_label = _section_label_map(schema)

    # section_id -> part_label
    sec_to_part = {}
    for part in schema.get("parts", []):
        for sid in part.get("section_ids", []):
            sec_to_part[sid] = part.get("label", part["id"])

    groups = []
    for sec in schema.get("sections", []):
        sid = sec["id"]
        part_label = sec_to_part.get(sid)
        if part_label is None:
            # Best-effort: part_7's sections are not listed under part_7 in this
            # schema (empty section_ids). Recover the part by the section label's
            # leading "Part N" token (e.g. "Part 7.1 ..." -> "Part 7") and reuse
            # the real parts[] label for that part number when available, so all of
            # Part 7's sections group under one header.
            label = sec.get("label", sid) or "Other"
            part_num = None
            toks = label.split()
            if len(toks) >= 2 and toks[0].lower() == "part":
                part_num = toks[1].split(".")[0]  # "7.1" -> "7"
            part_label = "Other"
            if part_num is not None:
                part_label = "Part " + part_num
                for p in schema.get("parts", []):
                    if p.get("label", "").lower().startswith("part " + part_num + "."):
                        part_label = p["label"]
                        break
        field_ids = [fid for fid in sec.get("fields", [])]
        groups.append((part_label, sec_label.get(sid, sid), field_ids))
    return groups


def _raw_value(field_values: dict, fid: str):
    """Extract the raw value for a field, accepting BOTH the primitive shape
    ({fid: "Smith"}) AND the real client wire shape ({fid: {"value": "Smith",
    "confirmed": true}}) that webFormConnection.ts form_state_response sends. The
    `confirmed` flag (and any other wrapper keys) are dropped -- the secretary reads
    the value, not the confirm-state."""
    v = field_values.get(fid, None)
    if isinstance(v, dict) and "value" in v:
        return v.get("value")
    return v


def _option_label(field: dict, raw) -> str:
    """For a radio/select field, map a stored option token to its human label.
    The client stores the option `value` token (e.g. 'P1_checkbox4[0]'); rendering
    only that token would force the model to guess option ordering. Resolve it to
    the label ('Yes ...') so the secretary reads a meaningful value."""
    opts = field.get("options") or []
    for o in opts:
        if isinstance(o, dict) and str(o.get("value")) == str(raw):
            return str(o.get("spoken_label") or o.get("label") or raw)
    return str(raw)


def _value_str(field: dict, field_values: dict, fid: str) -> str:
    raw = _raw_value(field_values, fid)
    if raw is None or raw == "":
        return EMPTY
    if isinstance(raw, bool):
        return "true" if raw else "false"
    # radio/select: render the option LABEL, not the opaque value token.
    if field.get("type") in ("radio", "select", "checkbox") and field.get("options"):
        return _option_label(field, raw)
    return str(raw)


def _options_str(field: dict) -> str:
    opts = field.get("options")
    if not opts:
        return ""
    labels = []
    for o in opts:
        if isinstance(o, dict):
            labels.append(str(o.get("label", o.get("value", ""))))
        else:
            labels.append(str(o))
    return " | options: [" + "; ".join(labels) + "]"


def _render_field(field: dict, fid: str, field_values: dict, shown_map: dict,
                  with_state: bool = True) -> str:
    """Render one field. with_state=True emits the `value=.. | shown=..` line
    (the full secretary context, for recall). with_state=False emits ONLY the
    static metadata (id/spoken/name/type/options/help) -- the value-free,
    session-INVARIANT catalog used as the cacheable prefix (the dynamic
    values+applicability ride a separate tail; see render_static_catalog)."""
    spoken = field.get("spoken_name", "")
    name = field.get("name", "") or field.get("label", "")
    ftype = field.get("type", "")
    help_obj = field.get("help") or {}
    instr = (help_obj.get("instructions") or "").strip()
    fmt_hint = (help_obj.get("format_hint") or "").strip()

    head = '  - id={fid} | "{spoken}"'.format(fid=fid, spoken=spoken)
    if name and name != spoken:
        head += ' ({name})'.format(name=name)
    head += ' | type={t}{opts}'.format(t=ftype, opts=_options_str(field))

    lines = [head]
    if with_state:
        value = _value_str(field, field_values, fid)
        shown = shown_map.get(fid, True)
        lines.append('    value={v} | shown={s}'.format(
            v=('"%s"' % value if value != EMPTY else EMPTY),
            s=("true" if shown else "false"),
        ))
    if instr:
        h = "    help: " + instr
        if fmt_hint:
            h += " (format: " + fmt_hint + ")"
        lines.append(h)
    elif fmt_hint:
        lines.append("    help: (format: " + fmt_hint + ")")
    # Verbatim official-booklet excerpts for this field (bd wsao.1). Multi-line
    # by design (headings per option/line); indented under the field entry so
    # the catalog's list structure stays scannable.
    details = (help_obj.get("details") or "").strip()
    if details:
        lines.append("    details: |")
        lines.extend(("      " + dl) if dl else "" for dl in details.splitlines())
    return "\n".join(lines)


def _render_form_reference(schema: dict) -> str:
    """Render the form-LEVEL reference floor (bd wsao.1): metadata.details
    (form-level guidance that attaches to no field) and metadata.booklet_text
    (the whole official instructions booklet, verbatim). Session-invariant, so
    it belongs in the cacheable static catalog; returns "" when neither is set
    (renders stay byte-identical for kits without them)."""
    meta = schema.get("metadata") or {}
    out = []
    form_details = (meta.get("details") or "").strip()
    if form_details:
        out.append("=== FORM-LEVEL GUIDANCE ===")
        out.append(form_details)
        out.append("")
    booklet = (meta.get("booklet_text") or "").strip()
    if booklet:
        out.append("=== OFFICIAL FORM INSTRUCTIONS (verbatim reference) ===")
        out.append(booklet)
        out.append("")
    return "\n".join(out)


def render_secretary_context(schema: dict, field_values: dict, shown_map: dict) -> str:
    """Render the grouped-by-section secretary context as plain text.

    field_values: flat {field_id: value} (FormSession.field_values shape).
    shown_map:    {field_id: bool} applicability, SEPARATE from value.
    """
    field_values = field_values or {}
    shown_map = shown_map or {}
    idx = _field_index(schema)

    out = []
    last_part = None
    for part_label, section_label, field_ids in _ordered_groups(schema):
        if part_label != last_part:
            out.append("=== {p} ===".format(p=part_label))
            last_part = part_label
        out.append("Section: {s}".format(s=section_label))
        for fid in field_ids:
            field = idx.get(fid)
            if field is None:
                continue
            out.append(_render_field(field, fid, field_values, shown_map))
        out.append("")  # blank line between sections
    reference = _render_form_reference(schema)
    if reference:
        out.append("")
        out.append(reference)
    return "\n".join(out).rstrip() + "\n"


def render_static_catalog(schema: dict) -> str:
    """Render the VALUE-FREE static catalog: per-field metadata only (id,
    spoken_name, name, type, options, help, section), NO current values and NO
    applicability. This is session-INVARIANT -- the correct content for a cacheable
    prefix (implicit or explicit). The dynamic values + applicability go in a
    separate tail (render_values_tail), so the cached prefix stays stable across
    secretary calls within a session even as answers change."""
    idx = _field_index(schema)
    out = []
    last_part = None
    for part_label, section_label, field_ids in _ordered_groups(schema):
        if part_label != last_part:
            out.append("=== {p} ===".format(p=part_label))
            last_part = part_label
        out.append("Section: {s}".format(s=section_label))
        for fid in field_ids:
            field = idx.get(fid)
            if field is None:
                continue
            out.append(_render_field(field, fid, {}, {}, with_state=False))
        out.append("")
    # Form-level reference floor (bd wsao.1) -- session-invariant, so it lives
    # in the cacheable prefix. Appended at the END so schemas without it render
    # byte-identically to the pre-wsao.1 catalog.
    reference = _render_form_reference(schema)
    if reference:
        out.append("")
        out.append(reference)
    return "\n".join(out).rstrip() + "\n"


def render_values_tail(schema: dict, field_values: dict, shown_map: dict) -> str:
    """Render the DYNAMIC tail: current value + applicability per field, keyed by
    id (no metadata -- that lives in the cached static catalog). This is the small,
    fresh, uncached part of a secretary request."""
    field_values = field_values or {}
    shown_map = shown_map or {}
    idx = _field_index(schema)
    out = ["CURRENT VALUES (id: value | shown):"]
    for fid in idx:
        value = _value_str(idx[fid], field_values, fid)
        shown = shown_map.get(fid, True)
        out.append("  %s: %s | shown=%s" % (
            fid, ('"%s"' % value if value != EMPTY else EMPTY),
            "true" if shown else "false"))
    return "\n".join(out) + "\n"


def estimate_tokens(text: str) -> int:
    """Best-effort token estimate. Uses tiktoken if available, else chars/4."""
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)
