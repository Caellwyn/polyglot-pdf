#!/usr/bin/env python3
"""One-command PDF -> draft FormSchema authoring pass (bd polyglot-pdf-7a9.12 / B1).

The shipped I-90-grade authoring tool: takes a fillable form PDF and emits a
schema-format-valid draft FormSchema (docs/schema_format.md /
backend/models/form_models.py shape) for a human to touch up in the schema-editor.

It reuses the validated scripts/bakeoff/ machinery:
  1. acroform_dump.py  -- deterministic PyMuPDF AcroForm dump (exact widget
     names, types, flags, tooltips, geometry) -- the anti-hallucination anchor.
  2. arm_llm_native.run -- the strong-LLM (Claude Opus via the local CLI, free
     in-env) pass that reasons over the dump + the PDF into a FormSchema.

PROMPT CHOICE (the B1 bake-off, on I-90, recorded in
docs/research/2026-06-15-7a9.12-i90-authoring-pass-findings.md): plain
"claude-hybrid" (raw AcroForm field list) vs the enriched bundle. The default is
set to the bake winner; --enriched / --plain override. The 7a9.11 finding (the
enriched bundle REGRESSES vs plain hybrid on the touch-up metrics) is why the
default is what it is -- big-form/table work stays deferred per the bead.

ASCII only (cp1252 safe).

Usage:
    python scripts/authoring/extract_form.py --pdf form-kits/i-90/form.pdf \
        --out form-kits/i-90/draft_schema.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

import fitz  # PyMuPDF -- page-1 text + doc.metadata for version extraction.

# Reuse the bakeoff machinery (the bead: "reuse the validated scripts/bakeoff/").
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))
sys.path.insert(0, os.path.join(_REPO, "scripts", "authoring"))
import acroform_dump  # noqa: E402
import arm_llm_native  # noqa: E402
import derive_sections  # noqa: E402 (deterministic form divisions, bd 6cfu.2)

# Confidence tiers for the version determination (bd polyglot-pdf-s4dp.2). A
# specific Edition/Rev pattern is HIGH; a generic bare-year/loose-OMB fallback is
# LOW; no recoverable version is NONE. Mirrors ExtractionInfo.extraction_confidence
# (backend/models/form_models.py) -- a single 0-1 float scoped to the version.
_CONF_HIGH = 0.9
_CONF_LOW = 0.4
_CONF_NONE = 0.0

# The B1 bake-off default (set from the recorded I-90 winner). plain=True means
# the claude-hybrid prompt (raw AcroForm list); plain=False the enriched bundle.
DEFAULT_PLAIN = True


def _has_usable_position(pos: object) -> bool:
    """True only for a pdf_position with a positive width AND height.

    The LLM frequently emits a placeholder rect (all-zero, or missing
    width/height) that is truthy as a dict but useless for the editor's
    click-to-jump mapping. A genuine AcroForm widget always has positive width
    and height, so we treat anything else as "no usable position" and let the
    deterministic dump-rect back-fill replace it (bd 7a9.18)."""
    if not isinstance(pos, dict):
        return False
    try:
        return float(pos.get("width") or 0) > 0 and float(pos.get("height") or 0) > 0
    except (TypeError, ValueError):
        return False


def _backfill_positions(schema: dict, dump_path: str) -> dict:
    """Deterministically set `pdf_position` on each field AND each option from the
    AcroForm dump (bd polyglot-pdf-5f41 extends the field-only pass, bd 7a9.18).

    The LLM is flaky at copying widget coordinates (the B1 bake measured pos 0%
    on both arms), but the dump HAS every widget's rect keyed by its exact name,
    and the draft copies that name verbatim into `pdf_field_name`. So we fill
    pdf_position from the dump for free -- a deterministic gain over either raw
    arm. Dump rects are 0-based pages; the gold/schema convention is 1-based, so
    we +1.

    Field-level: a field's position = the rect of the FIRST widget of its
    (first) pdf_field_name, or (when the field itself carries no name) the
    first option's pdf_field_name -- same convention as the pre-5f41 pass,
    except the name lookup is now suffix-aware too (a strict superset: it can
    fill fields whose leaf-name claim the old exact match missed).

    Option-level (new): for each option not already carrying a usable
    pdf_position, resolve its widget --
      a. option.pdf_field_name present: look up its widget group. A single
         widget wins outright; several widgets are disambiguated by
         option.pdf_on_value (matched against each widget's on_value), else the
         first widget wins (same first-wins convention as the field level).
      b. option.pdf_field_name absent but the FIELD has one and the option
         carries pdf_on_value (the shared-name radio-group shape): pick the
         widget in the field name's group whose on_value == pdf_on_value.
         When NO widget in the group carries an on_value at all, the group is
         a dropdown (combobox/listbox -- e.g. i-90's height selects), whose
         options are choice values of one shared widget rather than printed
         boxes: silently skipped, not unmatched.
      c. otherwise, or when the lookup finds nothing: recorded as unmatched
         (field id, option value, reason) -- never guessed.

    Name lookups are suffix-aware (schema_lint._match_dump_names' exact-then-
    dot-boundary-suffix convention): a schema's XFA leaf name (e.g.
    "P1_checkbox6c_Unit[1]") must resolve to the dump's fully-qualified path
    (e.g. "form1[0].#subform[0].P1_checkbox6c_Unit[1]") -- i-90 alone has 32
    option pdf_field_names that only resolve this way.

    Returns {"fields_filled": int, "options_filled": int, "unmatched": [...]}."""
    try:
        with open(dump_path, encoding="utf-8") as fh:
            dump = json.load(fh)
    except OSError:
        return {"fields_filled": 0, "options_filled": 0, "unmatched": []}

    sys.path.insert(0, _REPO)  # self-sufficient, like the other backend imports
    from backend.services.schema_lint import _match_dump_names  # noqa: E402

    dump_names = [f["name"] for f in dump.get("fields", []) if f.get("name")]

    name_to_rect: dict[str, dict] = {}
    name_to_widgets: dict[str, list[dict]] = {}
    for f in dump.get("fields", []):
        name = f.get("name")
        if not name:
            continue
        widgets = f.get("widgets", [])
        name_to_widgets[name] = widgets
        for w in widgets:
            r = w.get("rect")
            if r and name not in name_to_rect:
                name_to_rect[name] = r

    def rect_to_pos(r: dict) -> dict:
        return {"page": int(r["page"]) + 1, "x": r["x"], "y": r["y"],
                "width": r["width"], "height": r["height"]}

    def resolve_widgets(claim: str) -> list[dict]:
        """The widget list for a schema-side pdf_field_name claim, suffix-aware."""
        for name in _match_dump_names(claim, dump_names):
            widgets = name_to_widgets.get(name)
            if widgets:
                return widgets
        return []

    fields_filled = 0
    options_filled = 0
    unmatched: list[dict] = []

    for field in schema.get("fields", []):
        # Back-fill when the position is MISSING *or* DEGENERATE. The LLM often
        # emits a placeholder {page, x:0, y:0, width:0, height:0} -- a truthy dict
        # that a bare `if field.get("pdf_position")` would treat as already set,
        # leaving the zeros in place (the editor then can't map the field to the
        # PDF, so click-to-jump dies -- bd 7a9.18). A real widget always has a
        # positive width AND height, so a non-positive either means it needs the
        # deterministic dump rect.
        field_pfn = field.get("pdf_field_name")
        if not _has_usable_position(field.get("pdf_position")):
            # A field's position = the rect of its (first) pdf_field_name; for a
            # consolidated options[] field, use the first option's widget.
            pfn = field_pfn
            if not pfn:
                for o in (field.get("options") or []):
                    if o.get("pdf_field_name"):
                        pfn = o["pdf_field_name"]
                        break
            widgets = resolve_widgets(pfn) if pfn else []
            rect = (widgets[0].get("rect") if widgets else None) or name_to_rect.get(pfn)
            if rect:
                field["pdf_position"] = rect_to_pos(rect)
                fields_filled += 1

        for opt in (field.get("options") or []):
            if _has_usable_position(opt.get("pdf_position")):
                continue  # idempotent -- a usable option position is never re-derived
            opt_pfn = opt.get("pdf_field_name")
            on_value = opt.get("pdf_on_value")
            rect = None
            if opt_pfn:
                widgets = resolve_widgets(opt_pfn)
                if len(widgets) == 1:
                    rect = widgets[0].get("rect")
                elif len(widgets) > 1:
                    if on_value:
                        match = next(
                            (w for w in widgets if w.get("on_value") == on_value),
                            None,
                        )
                        rect = (match or widgets[0]).get("rect")
                    else:
                        rect = widgets[0].get("rect")  # first-wins, no on_value hint
            elif field_pfn and on_value:
                # Shared-name radio-group shape: the option has no name of its
                # own, only an on_value distinguishing it within the field's
                # widget group.
                widgets = resolve_widgets(field_pfn)
                if widgets and not any(w.get("on_value") for w in widgets):
                    # No widget in the group carries an on_value: this is not a
                    # toggle group but a dropdown (combobox/listbox -- e.g.
                    # i-90's height selects), where options are choice VALUES
                    # of one shared widget, not separate printed boxes. Nothing
                    # option-level to place; Preview keeps field-rect painting.
                    continue
                match = next(
                    (w for w in widgets if w.get("on_value") == on_value), None,
                )
                rect = match.get("rect") if match else None

            if rect:
                opt["pdf_position"] = rect_to_pos(rect)
                options_filled += 1
            elif opt_pfn or (field_pfn and on_value):
                # Only a genuine attempt (a name or a shared-group hint to resolve)
                # counts as unmatched -- an option with neither is simply not a
                # PDF-backed option (e.g. a web-only choice) and is silently skipped.
                reason = (
                    f"pdf_field_name {opt_pfn!r} not found in dump"
                    if opt_pfn else
                    f"no widget in {field_pfn!r} group with on_value {on_value!r}"
                )
                unmatched.append({
                    "field_id": field.get("id"),
                    "option_value": opt.get("value"),
                    "reason": reason,
                })

    return {
        "fields_filled": fields_filled,
        "options_filled": options_filled,
        "unmatched": unmatched,
    }


def _build_name_to_tu(dump_path: str) -> dict[str, str]:
    """Map each AcroForm widget NAME -> its /TU tooltip text from the dump.

    The dump groups widgets by field name and records the /TU (the long
    human-readable label embedded in the form) as widget["tu"] when present
    (acroform_dump.py). We key by field name -- the same join key the draft uses
    for `pdf_field_name` -- so the caller can attach a field's tooltip to its
    help.instructions for free (bd polyglot-pdf-s4dp.3). First /TU seen per name
    wins; names without any /TU are simply absent."""
    try:
        with open(dump_path, encoding="utf-8") as fh:
            dump = json.load(fh)
    except OSError:
        return {}
    name_to_tu: dict[str, str] = {}
    for f in dump.get("fields", []):
        name = f.get("name")
        if not name or name in name_to_tu:
            continue
        for w in f.get("widgets", []):
            tu = (w.get("tu") or "").strip()
            if tu:
                name_to_tu[name] = tu
                break
    return name_to_tu


def _field_pdf_name(field: dict) -> str | None:
    """The PDF widget name backing a field: its own pdf_field_name, else the first
    option's (a consolidated options[] field carries the name per option, exactly
    as _backfill_positions resolves a field's rect)."""
    pfn = field.get("pdf_field_name")
    if pfn:
        return pfn
    for o in (field.get("options") or []):
        if o.get("pdf_field_name"):
            return o["pdf_field_name"]
    return None


def _extract_instructions_from_dump(schema: dict, dump_path: str) -> int:
    """Populate each field's help.instructions from its /TU tooltip (bd s4dp.3).

    Deterministic and free: extraction otherwise leaves help.instructions blank,
    yet the AcroForm /TU text is already captured in the dump. For each field we
    join on pdf_field_name and, when a /TU exists, set help.instructions to it.

    We do NOT clobber an existing help.instructions the LLM pass may have written
    -- a real value already there wins; /TU only fills a genuine blank. Returns the
    number of fields filled."""
    name_to_tu = _build_name_to_tu(dump_path)
    if not name_to_tu:
        return 0
    filled = 0
    for field in schema.get("fields", []):
        help_obj = field.get("help") or {}
        if (help_obj.get("instructions") or "").strip():
            continue  # a real value already present -- do not overwrite
        pfn = _field_pdf_name(field)
        tu = name_to_tu.get(pfn) if pfn else None
        if tu:
            help_obj["instructions"] = tu
            field["help"] = help_obj
            filled += 1
    return filled


# NOTE: an earlier version had a deterministic `_correct_group_checkbox_type`
# that retyped a consolidated all-checkbox-widget field radio->checkbox_group.
# It was REMOVED (bd polyglot-pdf-w0eq): widget type cannot distinguish a
# single-select radio from a multi-select group -- both are implemented with
# checkbox widgets in these forms (i-90 has 16 legitimate radios built on
# checkbox widgets that the rule wrongly converted). Radio-vs-group is a SEMANTIC
# judgment from the printed label ("select one" vs "select all that apply") that
# only the LLM can make; the group-candidates hint (now default ON, bd qmxb)
# routes that decision to the model, and _complete_grouped_families only COMPLETES
# a group the LLM already typed (never retypes it). A mechanical type override
# fights the model's correct judgment, so we do not do it.


# logical_type (from the AcroForm dump) -> schema FieldType for a backfilled
# field. A recovered field is a SINGLE widget with no deterministic option set,
# so it must be a v2 type that is valid with zero options: `checkbox` (a boolean
# -- for any single toggle widget, checkbox OR radio) or `text` (for everything
# else, incl. combo/list dropdowns whose options we can't recover here). A human
# editor refines a recovered dropdown into a proper select. Anything typed with
# options (radio/select/checkbox_group) would fail v2's >=2-option/no-options
# strictness on a bare backfilled field, so we never mint those here.
_LOGICAL_TO_FIELD_TYPE = {
    "checkbox": "checkbox",
    "radio": "checkbox",  # a lone recovered radio widget is a boolean toggle
    "text": "text",
    # acroform_dump emits "combobox"/"listbox"/"signature" (the real strings); a
    # recovered dropdown becomes text (its options can't be recovered here -- an
    # editor re-types it to select), and a signature widget becomes text too.
    "combobox": "text",
    "listbox": "text",
    "signature": "text",
}


def _slugify_leaf(leaf: str) -> str:
    """A stable, ASCII field id from a widget leaf name (e.g. 'f1_16[0]' ->
    'f1_16_0'). Deterministic: same widget always yields the same id."""
    out = []
    for ch in leaf:
        out.append(ch if (ch.isalnum()) else "_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "widget"


def _complete_grouped_families(schema: dict, dump_path: str) -> dict:
    """Complete a PARTIALLY-grouped widget family in place (bd polyglot-pdf-qmxb).

    The extractor's LLM pass stochastically drops some option-widgets of a
    "select one/all of N checkboxes" question -- e.g. it modeled 1 of i-90's 5
    P2_checkbox3 widgets (bd 0nxh). group_candidates.find_group_candidates mines
    the dump for widget FAMILIES that belong to one logical question; when the LLM
    consolidated SOME-but-not-all of a family into a single field's options[], the
    missing members are almost certainly dropped options of THAT SAME field. This
    deterministically appends them as options -- WITHOUT changing the field's type.

    Type is never touched on purpose: single-select (radio) vs multi-select
    (checkbox_group) is a semantic read of the printed label that only the LLM can
    make (the widget-type retype that ignored this was built then removed -- bd
    w0eq, see the NOTE above _LOGICAL_TO_FIELD_TYPE). Here the LLM has ALREADY made
    that call (the field exists with a type); we only complete its option set, so
    we never re-open the retype trap.

    Fires ONLY when exactly ONE field owns the family (claims >=1 member via an
    option AND 0 < claimed < all). Every other case is a SKIP -- the family is
    split across fields (owners > 1), a false positive (0 claimed), or already
    complete (all claimed) -- and _backfill_unclaimed_widgets still guarantees no
    widget silently vanishes. Runs BEFORE that backfill so a completed member is
    not also minted as a loose duplicate field.

    Claim matching reuses schema_lint._match_dump_names / is_fillable_widget (the
    single source of truth). Returns {"fields_completed", "options_added"}."""
    sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))
    from group_candidates import find_group_candidates  # noqa: E402
    sys.path.insert(0, _REPO)
    from backend.services.schema_lint import (  # noqa: E402 single source of truth
        _match_dump_names, is_fillable_widget)
    try:
        with open(dump_path, encoding="utf-8") as fh:
            dump = json.load(fh)
    except OSError:
        return {"fields_completed": 0, "options_added": 0}

    families = find_group_candidates(dump)
    if not families:
        return {"fields_completed": 0, "options_added": 0}

    entries = [e for e in dump.get("fields", []) if isinstance(e, dict)]
    dump_names = [e.get("name") for e in entries if isinstance(e.get("name"), str)]

    # Map each dump widget name -> the field(s) whose OPTION claims it (a family is
    # only "owned" via consolidated options[], never via a field-level pfn -- a
    # field-level pfn is a single-widget field, not a group).
    fields = schema.get("fields", [])

    def _option_claims(field) -> set:
        claimed: set = set()
        for o in (field.get("options") or []):
            if isinstance(o, dict) and isinstance(o.get("pdf_field_name"), str):
                claimed.update(_match_dump_names(o["pdf_field_name"], dump_names))
        return claimed

    field_claims = [(f, _option_claims(f)) for f in fields]
    # Every widget claimed by ANY field via ANY route -- option pfn OR the
    # field-level pfn of a standalone single-widget field. A completion must NEVER
    # re-append a member already claimed elsewhere (that would double-claim the
    # widget -> dump-widget-multiclaim; bd rsy3/qmxb Opus review). Ownership is
    # still judged by OPTION claims only (a field-level pfn is a single-widget
    # field, not a group), but MISSING excludes anything any field already holds.
    all_claimed: set = set()
    for f in fields:
        pfn = f.get("pdf_field_name")
        if isinstance(pfn, str) and pfn:
            all_claimed.update(_match_dump_names(pfn, dump_names))
    for _f, c in field_claims:
        all_claimed |= c

    fields_completed = 0
    options_added = 0

    for fam in families:
        members = [m for m in fam.get("widgets", []) if isinstance(m, str)
                   and is_fillable_widget(dump, m)]
        member_set = set(members)
        if len(member_set) < 2:
            continue
        # Which fields claim ANY member (via an option)?
        owners = [(f, c & member_set) for f, c in field_claims if c & member_set]
        if len(owners) != 1:
            continue  # split across fields, or none -- deterministic merge is out of scope
        field, claimed_members = owners[0]
        # MISSING = members no field claims by ANY route (never re-append a widget
        # another field already holds -- that manufactures a multiclaim).
        missing = [m for m in members if m not in all_claimed]
        if not claimed_members or not missing:
            continue  # false positive (0 claimed) or already fully claimed elsewhere
        # Complete the family: append each missing widget as an option of THIS
        # field (placeholder value/label; a human editor + the repair pass refine
        # them). pdf_field_name is the coverage-critical part.
        opts = field.setdefault("options", [])
        existing_vals = {o.get("value") for o in opts if isinstance(o, dict)}
        for name in missing:
            leaf = name.split(".")[-1]
            val = _slugify_leaf(leaf)
            while val in existing_vals:
                val += "_x"
            existing_vals.add(val)
            opts.append({"value": val, "label": leaf, "pdf_field_name": name})
            options_added += 1
        fields_completed += 1

    return {"fields_completed": fields_completed, "options_added": options_added}


def _backfill_unclaimed_widgets(schema: dict, dump_path: str) -> int:
    """Append a minimal field for every fillable AcroForm widget NO field claims
    (bd polyglot-pdf-w0eq, P6.1c).

    The LLM extraction pass stochastically omits a field entirely -- re-runs on w7
    are the SAME PDF, yet a re-extraction drops a different widget each run, and
    the loss was silent (lint flagged only OVER-claim). This deterministic step
    closes the gap: any USER-FILLABLE dump widget (per schema_lint's
    is_fillable_widget -- buttons + machine barcodes excluded) unclaimed by any
    field's pdf_field_name / option pdf_field_name is added back as a basic field,
    typed from its dump logical_type and positioned from its dump rect. The
    recovered field is functional-but-plain -- a human editor refines its label;
    the point is that NO widget silently vanishes. Returns the number added.

    Section filing is NOT done here (bd polyglot-pdf-6cfu.2): the recovered
    field carries a placeholder section_id="" and the deterministic division
    pass (derive_sections.derive_and_apply, pipeline step 3e) re-files EVERY
    field -- recovered ones included -- into derived sections right after,
    using the dump rect this step attaches. A positionless recovery lands in
    the derived 'To review (unplaced)' bucket, so nothing is orphaned.

    Claim matching + fillability reuse schema_lint's helpers (single source of
    truth) so backfill and the under-claim lint rule can never disagree on what
    counts as a coverage gap (bd polyglot-pdf-w0eq)."""
    sys.path.insert(0, _REPO)  # self-sufficient, like the other backend imports
    from backend.services.schema_lint import (  # noqa: E402 single source of truth
        _match_dump_names, is_fillable_widget)
    try:
        with open(dump_path, encoding="utf-8") as fh:
            dump = json.load(fh)
    except OSError:
        return 0
    entries = [e for e in dump.get("fields", []) if isinstance(e, dict)]
    dump_names = [e.get("name") for e in entries if isinstance(e.get("name"), str)]
    if not dump_names:
        return 0

    # Widgets already claimed by any field / option (suffix-aware, EXACTLY the
    # lint/filler convention -- reused, not reimplemented).
    claimed: set = set()
    for f in schema.get("fields", []):
        for c in [f.get("pdf_field_name")] + [
            o.get("pdf_field_name") for o in (f.get("options") or [])
            if isinstance(o, dict)
        ]:
            if isinstance(c, str) and c:
                claimed.update(_match_dump_names(c, dump_names))

    by_name = {e["name"]: e for e in entries if isinstance(e.get("name"), str)}

    def _rect_pos(name):
        e = by_name.get(name) or {}
        for w in e.get("widgets", []):
            r = w.get("rect")
            if r:
                return {"page": int(r["page"]) + 1, "x": r["x"], "y": r["y"],
                        "width": r["width"], "height": r["height"]}
        return None

    existing_ids = {f.get("id") for f in schema.get("fields", [])}
    added = 0
    for name in dump_names:
        if name in claimed:
            continue
        if not is_fillable_widget(dump, name):
            continue  # buttons + machine-generated barcodes are not coverage gaps
        logical = (by_name.get(name) or {}).get("logical_type")
        leaf = name.split(".")[-1]
        fid = _slugify_leaf(leaf)
        while fid in existing_ids:
            fid = fid + "_x"
        existing_ids.add(fid)
        # A degenerate leaf (e.g. a name ending in ".") yields an empty display
        # label; fall back to the id so name/spoken_name are never blank.
        label = leaf or fid
        pos = _rect_pos(name)
        field = {
            "id": fid,
            "name": label,  # plain placeholder label -- editor refines it
            "spoken_name": label.replace("_", " "),
            "type": _LOGICAL_TO_FIELD_TYPE.get(logical, "text"),
            # Placeholder only: the deterministic division pass (step 3e)
            # re-files every field into derived sections right after this.
            "section_id": "",
            "pdf_field_name": name,
        }
        if pos:
            field["pdf_position"] = pos
        # Every backfilled type (checkbox / text) is valid with NO options: a v2
        # checkbox is a boolean carrying its widget in pdf_field_name, and text
        # takes no options. We deliberately never mint an options-bearing type
        # here (radio/select need >=2 options a bare widget can't supply).
        schema.setdefault("fields", []).append(field)
        added += 1
    return added


def _parse_instructions_pdf(path: str) -> str:
    """Extract the full text of an optional instructions PDF (bd s4dp.3).

    A straightforward whole-document text pass (no LLM, no structured ingestion --
    deep mapping is explicitly out of scope for this bead). Returns the joined
    page text, or "" if the file is unreadable. Pages are joined with form-feeds
    so the per-field matcher can keep page boundaries if it wants them."""
    try:
        doc = fitz.open(path)
    except Exception:  # bad/missing/corrupt file -> no enrichment (never a crash)
        return ""
    try:
        return "\n\f\n".join(doc[i].get_text() for i in range(doc.page_count))
    finally:
        doc.close()


# A field's label often starts with an item/line marker the instructions PDF
# reuses verbatim ("Item Number 1.", "Line 6a", "Part 2."). We match a field to
# its instructions paragraph by locating the field's LABEL text in the PDF; the
# label is the most reliable shared key (the bead scopes this to a straightforward
# text merge, not structured ingestion).
def _instructions_paragraphs(instructions_text: str) -> list[str]:
    """Split the instructions PDF text into trimmed, non-empty paragraphs (blank-
    line delimited). Form-feeds (page breaks) count as paragraph breaks too."""
    raw = re.split(r"\n\s*\n|\f", instructions_text or "")
    return [p.strip() for p in raw if p.strip()]


def _collapse_ws(text: str) -> str:
    """Collapse every run of whitespace (incl. newlines) to a single space and
    strip. Used to make instructions-PDF label matching line-break-agnostic
    (PyMuPDF wraps text mid-label) -- Codex PR #274."""
    return re.sub(r"\s+", " ", text or "").strip()


def _field_match_label(field: dict) -> str:
    """The text used to match a field against an instructions paragraph: the
    field's `name` (the backend FormField's required "Display label" -- the
    concise, specific label like "Family Name (Last Name)"), falling back to
    `label` (a verbose breadcrumb some drafts also carry) only when `name` is
    absent. Matching on `name` is BOTH the contract-correct key (a draft may carry
    only `name`, never `label` -- Codex PR #274) AND the better match (the breadcrumb
    `label` repeats its "Part N. ..." prefix across every field in the part)."""
    return field.get("name") or field.get("label") or ""


def _match_instruction_for_label(label: str, paragraphs: list[str]) -> str | None:
    """Find the instructions paragraph that best matches a field's label.

    A straightforward, deterministic text merge (bd s4dp.3): we look for a
    paragraph that CONTAINS the field's label as a case-insensitive substring
    (labels are short and specific -- "Family Name (Last Name)", "Alien Registration
    Number"), preferring the SHORTEST such paragraph (the tightest, most field-
    specific passage rather than a sprawling section header). Returns None when no
    paragraph mentions the label, so /TU (or nothing) stands. Very short labels
    (< 4 non-space chars) are skipped -- they match too loosely to be reliable.

    WHITESPACE-NORMALIZED on both sides before matching (Codex PR #274): PyMuPDF
    wraps extracted text with newlines, so a label like "Family Name (Last Name)"
    would NOT substring-match a paragraph rendered "Family Name\n(Last Name): ..."
    -- the common PDF line-break layout. Collapsing all runs of whitespace to a
    single space on the label AND each paragraph makes the match line-break-agnostic
    (we return the ORIGINAL paragraph text so the appended help keeps its layout)."""
    key = _collapse_ws(label or "")
    if len(key.replace(" ", "")) < 4:
        return None
    key_low = key.lower()
    # Match on a whitespace-collapsed copy of each paragraph, but return the
    # ORIGINAL (so the appended help text preserves the source layout).
    hits = [p for p in paragraphs if key_low in _collapse_ws(p).lower()]
    if not hits:
        return None
    return min(hits, key=len)


def _enrich_instructions_from_pdf(schema: dict, instructions_pdf_path: str) -> int:
    """Enrich help.instructions from an optional instructions PDF (bd s4dp.3).

    For each field whose name appears in the instructions text, append the
    matched paragraph to help.instructions (after any /TU baseline, separated by a
    blank line). A field with no match keeps whatever /TU gave it. Returns the
    number of fields enriched. A merge, never a clobber: the instructions text is
    ADDED to the /TU baseline so both sources survive.

    Matches on the field's `name` (fallback `label`) via _field_match_label -- the
    backend contract makes `name` the display label and `label` optional, so a
    contract-minimal draft has only `name` (Codex PR #274)."""
    instructions_text = _parse_instructions_pdf(instructions_pdf_path)
    paragraphs = _instructions_paragraphs(instructions_text)
    if not paragraphs:
        return 0
    enriched = 0
    for field in schema.get("fields", []):
        passage = _match_instruction_for_label(_field_match_label(field), paragraphs)
        if not passage:
            continue
        help_obj = field.get("help") or {}
        existing = (help_obj.get("instructions") or "").strip()
        # Skip only when the passage is ALREADY captured by the existing text
        # (passage in existing) -- a real form sometimes uses the instructions
        # sentence verbatim as its /TU. Do NOT skip the reverse case (existing in
        # passage): when the /TU baseline is just a SUBSTRING of the richer
        # instructions paragraph, that paragraph is exactly the enrichment we want
        # to append (bd s4dp.3 fresh-eyes -- the old `existing in passage` arm
        # silently dropped richer help, contradicting the "enriches when provided"
        # exit criterion).
        if existing and passage in existing:
            continue
        help_obj["instructions"] = f"{existing}\n\n{passage}" if existing else passage
        field["help"] = help_obj
        enriched += 1
    return enriched


# Month names for the IRS "(Rev. December 2024)" form-revision style.
_MONTHS = (
    "January February March April May June July August September October "
    "November December"
).split()
_MONTH_RE = "|".join(_MONTHS)


def extract_version_metadata(page1_text: str, doc_title: str = "") -> dict:
    """Deterministically recover a form's version metadata from its page-1 text +
    PDF title (bd polyglot-pdf-s4dp.2). No LLM. Pure (text in, dict out) so it is
    trivially unit-testable; `_extract_version_metadata_from_doc` wraps a PyMuPDF
    doc.

    Real forms carry version info in several shapes -- USCIS "Edition MM/DD/YY",
    IRS "(Rev. Month Year)", IRS year-only "2025" -- and some carry none. We match
    in DESCENDING specificity (first hit wins per field) and attach a single
    `version_confidence` (0-1): HIGH for a specific Edition/Rev pattern, LOW for a
    generic bare-year/loose-OMB fallback, NONE when nothing is recoverable (the
    version then degrades to the sentinel "unknown", never "draft"/blank).

    Only keys that were actually found are returned (so a caller can merge without
    clobbering), EXCEPT `version` + `version_confidence`, which are always present
    (version may be "unknown"). Absent fields (e.g. a form with no expiration) are
    simply omitted.
    """
    text = page1_text or ""
    title = doc_title or ""
    out: dict = {}

    # --- form_number: "Form I-90" / "Form W-7" / "Form 1040" (title-first) ------
    # Generalizes the old (I-\d+)-only regex to any USCIS/IRS form id.
    fn = re.search(r"Form\s+([A-Z]{0,3}-?\d{1,4}[A-Z]?)", title) \
        or re.search(r"Form\s+([A-Z]{0,3}-?\d{1,4}[A-Z]?)", text)
    if fn:
        out["form_number"] = fn.group(1).strip()

    # --- edition_date: USCIS "Edition MM/DD/YY" (canonical MM/DD/YY string) ------
    edition = re.search(r"Edition\s+(\d{2})/(\d{2})/(\d{2,4})", text)
    edition_str = None
    if edition:
        mm, dd, yy = edition.groups()
        yy = yy[-2:]  # canonical 2-digit year, matching the model's "01/20/25"
        edition_str = f"{mm}/{dd}/{yy}"
        out["edition_date"] = edition_str

    # --- version (human-facing revision label) + confidence ---------------------
    # Specificity order: Edition value -> "Rev. Month Year" -> a year in a FORM-
    # VERSION context -> unknown. The bare-year fallback is SCOPED (Codex PR #263):
    # an UNSCOPED `\b20\d{2}\b` over all page-1 text would grab an expiration or
    # other stray date (e.g. "Expires 02/28/2027" -> version "2027"), making a
    # version-less form look versioned and misleading the outdated-revision check.
    # A year is only a version when it sits in the TITLE (e.g. "2025 Form 1040") or
    # immediately adjacent to "Form <id>" on page 1 -- the IRS year-only header
    # convention -- never an arbitrary date elsewhere on the page.
    rev = re.search(rf"Rev\.?\s+((?:{_MONTH_RE})\s+\d{{4}})", text) \
        or re.search(rf"Rev\.?\s+((?:{_MONTH_RE})\s+\d{{4}})", title)
    # A bare year is a version ONLY when adjacent to "Form <id>" -- in the title
    # ("2025 Form 1040" or "Form 1040 2025") or on page 1. An UNSCOPED year (in
    # either title or text) would promote an expiration/effective year (Codex
    # PR #263 r1+r2). `_FORM_ID` is the form-number token used in several patterns.
    _FORM_ID = r"[A-Z]{0,3}-?\d{1,4}[A-Z]?"
    year_ctx = (
        re.search(rf"(20\d{{2}})\s+Form\s+{_FORM_ID}", title)
        or re.search(rf"Form\s+{_FORM_ID}\s+(20\d{{2}})", title)
        or re.search(rf"Form\s+{_FORM_ID}\s*\n?\s*(20\d{{2}})\b", text)
    )
    if edition_str:
        out["version"] = edition_str
        out["version_confidence"] = _CONF_HIGH
    elif rev:
        out["version"] = rev.group(1).strip()
        out["version_confidence"] = _CONF_HIGH
    elif year_ctx:
        out["version"] = year_ctx.group(1)
        out["version_confidence"] = _CONF_LOW  # generic but form-version-scoped
    else:
        out["version"] = "unknown"
        out["version_confidence"] = _CONF_NONE

    # --- omb_number: "OMB No. NNNN-NNNN" (specific) -> loose NNNN-NNNN (fallback)
    omb = re.search(r"OMB\s+No\.?\s*(\d{4}-\d{4})", text)
    if omb:
        out["omb_number"] = omb.group(1)
    else:
        loose = re.search(r"\b(\d{4}-\d{4})\b", text)
        if loose:
            out["omb_number"] = loose.group(1)
            # A loose OMB shouldn't UPGRADE confidence, but if the version was the
            # weakest tier (unknown), a found OMB is at least some provenance.
            if out.get("version_confidence", 0.0) == _CONF_NONE:
                out["version_confidence"] = _CONF_LOW

    # --- expiration_date: "Expires MM/DD/YYYY" (no fallback -- wrong is worse) ---
    exp = re.search(r"Expires\s+(\d{2})/(\d{2})/(\d{4})", text)
    if exp:
        mm, dd, yyyy = exp.groups()
        out["expiration_date"] = f"{mm}/{dd}/{yyyy}"

    # --- agency (USCIS / IRS string presence) -----------------------------------
    if ("U.S. Citizenship and Immigration Services" in text) or ("USCIS" in text):
        out["agency"] = "U.S. Citizenship and Immigration Services"
    elif ("Internal Revenue Service" in text) or ("IRS" in text):
        out["agency"] = "Internal Revenue Service"

    return out


def _extract_version_metadata_from_doc(doc: "fitz.Document") -> dict:
    """Thin PyMuPDF wrapper over extract_version_metadata: page-1 text + title."""
    page1 = doc[0].get_text() if doc.page_count else ""
    title = (doc.metadata or {}).get("title", "") or ""
    return extract_version_metadata(page1, title)


def _normalize_for_schema(schema: dict) -> dict:
    """Fill required-but-missing FormSchema fields with draft placeholders so a
    fresh extraction is schema-format-valid out of the box (the human refines
    them in the editor). The extractor arms reliably emit field structure +
    form_metadata.title but omit a few required scalars (e.g.
    form_metadata.version); supply safe defaults rather than reject the draft."""
    schema.setdefault("source", "pdf")
    meta = schema.setdefault("form_metadata", {})
    meta.setdefault("title", "Untitled form (draft)")
    # "unknown" (not "draft") is the no-version sentinel: extract_version_metadata
    # already populated a real version (or "unknown") before normalize runs; this
    # only covers the path where version metadata was never attempted (bd s4dp.2).
    meta.setdefault("version", "unknown")
    meta.setdefault("language", "en")
    schema.setdefault("sections", [])
    schema.setdefault("fields", [])
    return schema


# Extractor identity stamped into extraction_info (bd polyglot-pdf-l1a9). Bump
# on a breaking change to the pipeline's output shape, not on routine edits.
EXTRACTOR_VERSION = "extract_form-v1"


def _stamp_extraction_info(schema: dict) -> None:
    """Stamp fresh extraction provenance (bd polyglot-pdf-l1a9).

    No modern writer existed for extraction_info (only the retired
    prior_extractor stamped placeholders), so every extracted kit failed the
    publish gate's "extraction_info required for PDF forms" check (HTTP 422 at
    mark-complete) -- the actual W-7 blocker the sprint-17 forensics found.
    Always stamped fresh: a new extraction IS new provenance.

    extraction_confidence uses the documented 0.0 = "not a measured quantity"
    convention: the ledger (field<->widget claims) is deterministic, but the
    LLM's labels always need human review -- which is what
    manual_review_required=True states. The model has no unknown-sentinel for
    the float (changing it is out of sprint-17 scope).
    """
    schema["extraction_info"] = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extraction_confidence": 0.0,
        "extractor_version": EXTRACTOR_VERSION,
        "manual_review_required": True,
    }


def _check_dump_coverage(schema: dict, dump: dict | None) -> list[str]:
    """Fillable dump widgets claimed by NO field/option, post-backfill (bd
    polyglot-pdf-l1a9).

    _backfill_unclaimed_widgets deterministically claims every fillable widget
    the LLM missed, so by the time this runs an unclaimed fillable widget means
    the PIPELINE itself failed -- fail loudly (the caller records it, prints
    COVERAGE-FAILED, and the tri-state exit classifies the draft as ISSUES),
    never ship it silently. Buttons/barcodes are excluded via schema_lint's
    is_fillable_widget, and claims resolve with the same exact-or-dot-suffix
    rule as the lint dump rules (_match_dump_names) -- one matching convention,
    no drift. Returns sorted unclaimed names; [] when covered OR when the dump/
    lint module is unavailable (same graceful-import contract as the sibling
    helpers)."""
    if not dump:
        return []
    try:
        sys.path.insert(0, _REPO)
        from backend.services.schema_lint import (  # noqa: E402
            _match_dump_names, is_fillable_widget,
        )
    except Exception:  # pragma: no cover - env-dependent
        return []
    names = [e.get("name") for e in (dump.get("fields") or [])
             if isinstance(e, dict) and isinstance(e.get("name"), str)]
    claimed: set[str] = set()
    for f in (schema.get("fields") or []):
        if not isinstance(f, dict):
            continue
        for claim in [f.get("pdf_field_name")] + [
            o.get("pdf_field_name") for o in (f.get("options") or [])
            if isinstance(o, dict)
        ]:
            if isinstance(claim, str) and claim:
                claimed.update(_match_dump_names(claim, names))
    return sorted(n for n in names
                  if n not in claimed and is_fillable_widget(dump, n))


def _validate_schema(schema: dict) -> tuple[bool, str]:
    """Validate the draft against the canonical Pydantic FormSchema, if importable.

    Returns (ok, detail). `ok=False` is the tool's failure signal -- main() exits
    non-zero and warns on stderr. The IMPORT failure is handled gracefully (not a
    crash): if the backend model cannot be imported in this environment, we fall
    back to a structural check (required top-level keys + a non-empty fields list)
    so the tool still runs standalone, and say which check ran in the detail."""
    try:
        sys.path.insert(0, _REPO)
        from backend.models.form_models import FormSchema  # noqa: E402
    except Exception as exc:  # pragma: no cover - env-dependent
        missing = [k for k in ("source", "form_metadata", "fields") if k not in schema]
        if missing or not schema.get("fields"):
            return False, f"structural check failed (missing {missing or 'fields'}); "\
                          f"backend model unavailable: {exc}"
        return True, f"structural check passed (backend Pydantic model unavailable: {exc})"
    try:
        FormSchema.model_validate(schema)
        return True, "validated against backend FormSchema (Pydantic)"
    except Exception as exc:
        return False, f"FormSchema validation failed: {str(exc)[:400]}"


def _repair_schema(schema: dict, dump: dict | None) -> tuple[dict, dict]:
    """Run the deterministic repair pass (bd h76m.13, P5.2) over the draft.

    Returns (schema_to_continue_with, report). The report rides in
    _bakeoff.authoring.repair: {applied, repairs[], alias_hits} or
    {skipped}/{failed}. Import failure degrades gracefully (same contract as
    _validate_schema/_lint_schema). A RepairError (hallucinated widgets) is
    LOUD -- stderr + failed report -- but still writes the unrepaired draft
    for inspection (P5.3 owns exit semantics)."""
    try:
        sys.path.insert(0, _REPO)
        from backend.services.schema_repair import (  # noqa: E402
            RepairError, alias_hit_count, repair,
        )
    except Exception as exc:  # pragma: no cover - env-dependent
        return schema, {"skipped": f"schema_repair unavailable: {exc}"}
    try:
        repaired, repairs = repair(schema, dump)
    except RepairError as exc:
        print(f"REPAIR-FAILED: {exc}", file=sys.stderr)
        return schema, {"failed": str(exc)[:400]}
    substantive = [r for r in repairs if r["action"] != "alias-hit-rate"]
    return repaired, {
        "applied": sum(1 for r in substantive if not r.get("error")),
        "dropped": sum(1 for r in substantive if r.get("error")),
        "alias_hits": alias_hit_count(repairs),
        "repairs": repairs,
    }


def _lint_schema(schema: dict, dump: dict | None) -> dict:
    """Run backend/services/schema_lint over the draft (bd h76m.5, P2.1).

    Returns the JSON-ready report stored under _bakeoff.authoring.lint:
    {errors, warnings, findings[]}. Import failure degrades gracefully (same
    contract as _validate_schema's fallback) so the tool still runs standalone.
    """
    try:
        sys.path.insert(0, _REPO)
        from backend.services.schema_lint import lint_schema  # noqa: E402
    except Exception as exc:  # pragma: no cover - env-dependent
        return {"errors": None, "warnings": None,
                "skipped": f"schema_lint unavailable: {exc}"}
    findings = lint_schema(schema, dump)
    return {
        "errors": sum(1 for f in findings if f.severity == "ERROR"),
        "warnings": sum(1 for f in findings if f.severity == "WARNING"),
        "findings": [f.as_dict() for f in findings],
    }


def _bake_option_translations(schema: dict, model: str | None = None) -> dict:
    """Bake FieldOption.label_translations for every supported spoken language
    (bd polyglot-pdf-2h9j). The shared implementation lives in
    backend/services/option_translation.py::bake_label_translations (also used
    by the standalone CLI translate_option_labels.py and the hosted editor
    route); this wrapper only handles authoring-pipeline concerns.

    FAIL-OPEN by contract: extraction NEVER fails because translation failed --
    any error is returned as a report dict, never raised (same graceful-degrade
    contract as _lint_schema). VERTEX-ONLY (maintainer directive 2026-07-28;
    bd polyglot-pdf-f3lm / w99b): the AI Studio gate is closed, so there is no
    GEMINI_API_KEY path and no credential pre-gate -- a bare local run uses
    ADC, the hosted route its service account, and an auth failure surfaces
    through the fail-open handler below like any other error.
    """
    try:
        import asyncio  # noqa: E402 -- authoring script stays sync elsewhere
        sys.path.insert(0, _REPO)
        from backend.adapters.text_ai_gemini import TextAIGemini  # noqa: E402
        from backend.services.option_translation import (  # noqa: E402
            bake_label_translations,
        )
        from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47  # noqa: E402

        model = model or os.getenv("OPTION_TRANSLATION_MODEL", "gemini-2.5-pro")
        # 2.5-pro cannot disable thinking; bound it (W6 pattern). The fallback
        # chain is disabled so a deliberately chosen tier fails loud (and
        # fail-open catches it) instead of silently degrading to lite.
        thinking = 512 if "pro" in model else None
        text_ai = TextAIGemini(
            model=model, vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            fallback_models=(), thinking_budget=thinking)
        languages = {n: c for n, c in SPOKEN_LANGUAGE_BCP47.items()
                     if n != "english"}
        report = asyncio.run(bake_label_translations(schema, text_ai, languages))
        report["model"] = model
        return report
    except Exception as exc:  # noqa: BLE001 -- fail-open by contract
        return {"failed": f"{type(exc).__name__}: {exc}"}


def _translation_flag_summary(report: dict) -> str | None:
    """The console flag-count line for a bake report, or None when flag-free
    (bd polyglot-pdf-9djc). The full findings ride the draft verbatim (the
    report is stored at _bakeoff.authoring.option_translation, flags included)
    and the editor ValidationPanel re-renders them from there; the console
    gets counts only -- flag messages can quote foreign-script strings, which
    the cp1252 console rule bars from printing."""
    flags = report.get("flags") or []
    if not flags:
        return None
    by_rule: dict = {}
    for f in flags:
        rule = str(f.get("rule", "?")) if isinstance(f, dict) else "?"
        by_rule[rule] = by_rule.get(rule, 0) + 1
    summary = ", ".join(f"{r}={n}" for r, n in sorted(by_rule.items()))
    return (f"translation flags: {len(flags)} ({summary}) -- recorded in "
            f"_bakeoff.authoring.option_translation.flags (WARNINGs, "
            f"human-review worklist)")


def _enrich_guidance(schema: dict, pdf_path: str,
                     instructions_pdf: str | None,
                     name_to_tu: dict[str, str],
                     model: str | None = None) -> dict:
    """The sprint-16 guidance-enrichment stage (bd wsao.6): author
    help.instructions/details/format_hint + the form-level details from the
    official booklet, judge + rectify (KEEP rule), and apply under the
    provenance guard -- all via scripts/authoring/enrich_instructions.py.

    FAIL-OPEN by contract, mirroring _bake_option_translations: extraction
    NEVER fails because enrichment failed. When the LLM stage is unavailable
    (no authoring model, no booklet-judge credentials -> the engine's KEEP
    rule already empties unverified text) or raises, the pre-wsao naive
    substring match (_enrich_instructions_from_pdf) runs as the fallback so
    an explicit --instructions-pdf still adds SOMETHING, exactly as before.
    """
    booklet_dir = os.path.dirname(os.path.abspath(pdf_path))
    booklet_path: str | None = None
    try:
        import enrich_instructions as ei  # noqa: E402  (same directory)
        booklet_path = ei.find_booklet(booklet_dir, instructions_pdf)
        if not booklet_path:
            return {"skipped": "no instructions booklet found"}
        askable = ei.askable_fields(schema)
        max_fields = int(os.getenv("GUIDANCE_MAX_FIELDS", "250"))
        if len(askable) > max_fields:
            # The stage's LLM cost/latency scales as fields x booklet (the
            # full booklet rides EVERY authoring + judge chunk) and runs
            # inside the extraction subprocess timeout -- an unbounded form
            # could time the whole extraction out (wsao.6 outer review).
            # Oversize forms defer to the standalone CLI, which has no
            # request deadline. The oversize case is a DEGRADED path like
            # the others, so the naive fallback still runs (pre-wsao parity
            # -- reviewer 2: returning bare here gave an oversize form with
            # a booklet ZERO enrichment where the old 3c step enriched it).
            report = {"skipped": f"{len(askable)} askable fields > "
                                 f"GUIDANCE_MAX_FIELDS={max_fields} -- run "
                                 f"scripts/authoring/"
                                 f"enrich_instructions.py standalone"}
            try:
                report["fallback_enriched"] = \
                    _enrich_instructions_from_pdf(
                        schema, instructions_pdf or booklet_path)
            except Exception:  # noqa: BLE001
                pass
            return report
        model = model or ei.DEFAULT_MODEL
        booklet = ei.booklet_text(booklet_path)
        form_name = ((schema.get("form_metadata") or {}).get("title")
                     or os.path.basename(pdf_path))
        result = ei.enrich_schema(schema, booklet, form_name, model,
                                  ei.DEFAULT_CHUNK)
        flags = ei.verify_and_rectify(schema, result["proposals"], booklet,
                                      form_name, model)
        summary = ei.apply_proposals(schema, result["proposals"], booklet,
                                     flags, model, ei.JUDGE_MODEL,
                                     tu_map=name_to_tu)
        # apply_proposals stores the provenance block on the schema, but
        # extract() REPLACES _bakeoff.authoring wholesale below -- so lift
        # the block into the returned report for the authoring literal.
        block = (schema.get("_bakeoff", {}).get("authoring", {})
                 .get("instructions_enrich") or {})
        report = dict(block)  # keeps the FLAGS LIST + provenance intact
        report.update(
            written=summary.get("written", 0),
            skipped_human=summary.get("skipped_human", 0),
            # Carry the hallucinated-id count into the PIPELINE report too --
            # it exists to make a systematic model id-echo failure visible
            # instead of looking like "the booklet had nothing to say", and
            # the hosted path is the one that actually runs in production
            # (bd anim outer review: the CLI printed it, this dropped it).
            unmatched_proposal_ids=summary.get("unmatched_proposal_ids") or [],
            booklet=os.path.basename(booklet_path),
            tokens=result.get("tokens", []))
        # Judge-unavailable is caught INSIDE verify_and_rectify (the KEEP
        # rule empties every proposal + flags), so it never reaches the
        # except below -- without this, a credential-less local run
        # produced EMPTY guidance where the pre-wsao path produced naive
        # substring content (outer review). Behavior parity: run the naive
        # fallback for an explicit --instructions-pdf, exactly as the
        # exception path does.
        if any(isinstance(f, dict)
               and f.get("rule") == "instructions-enrich-unavailable"
               for f in (flags or [])):
            report["unavailable"] = True
            try:
                # the AUTO-DISCOVERED booklet feeds the fallback too --
                # gating on the explicit flag alone gave the default
                # discovery path strictly weaker degraded-mode coverage
                # (outer review finding 4)
                report["fallback_enriched"] = \
                    _enrich_instructions_from_pdf(schema, booklet_path)
                # The fallback APPENDS to help.instructions AFTER the tu
                # bootstrap hashed the pre-append text -- without a refresh
                # the seeded records go stale and every touched field is
                # silently human-locked on the next credentialed run
                # (outer review finding 1, reproduced). The appended text
                # is machine text, so refreshing keeps it machine-owned.
                by_id = {f.get("id"): f for f in schema.get("fields", [])
                         if isinstance(f, dict)}
                for fid, rec in (report.get("provenance") or {}).items():
                    if isinstance(rec, dict) and rec.get("source") == "tu":
                        fld = by_id.get(fid) or {}
                        help_obj = fld.get("help") \
                            if isinstance(fld.get("help"), dict) else {}
                        cur = help_obj.get("instructions")
                        rec["instructions_sha1"] = ei._sha1(
                            cur if isinstance(cur, str) else "")
            except Exception:  # noqa: BLE001
                pass
        return report
    except Exception as exc:  # noqa: BLE001 -- fail-open by contract
        fallback = 0
        fallback_src = instructions_pdf or booklet_path
        if fallback_src:
            try:
                fallback = _enrich_instructions_from_pdf(schema,
                                                         fallback_src)
            except Exception:  # noqa: BLE001
                pass
        return {"failed": f"{type(exc).__name__}: {exc}",
                "fallback_enriched": fallback}


def extract(pdf_path: str, out_path: str, *, plain: bool = DEFAULT_PLAIN,
            model: str = "claude-opus-5", keep_dump: bool = False,
            instructions_pdf: str | None = None,
            group_candidates: bool = True,
            division_cap: int = derive_sections.DEFAULT_CAP,
            translate_options: bool = True,
            translation_model: str | None = None,
            enrich_guidance: bool = True,
            guidance_model: str | None = None) -> dict:
    """Run the full PDF -> draft-schema pass and write `out_path`. Returns the
    draft dict (with a `_bakeoff` provenance block).

    instructions_pdf: optional path to the form's official instructions PDF. When
    given, its text enriches each field's help.instructions on top of the /TU
    baseline (bd polyglot-pdf-s4dp.3); when absent, help.instructions is /TU-only.

    division_cap (bd 6cfu.2): the display-sanity cap on fields per derived
    section (derive_sections.DEFAULT_CAP; splits are balanced).

    group_candidates (bd h76m.12): when True, the prompt carries the
    deterministic pre-grouping candidates block (suggest, don't decide --
    see scripts/bakeoff/group_candidates.py). DEFAULT ON (bd qmxb): the
    h76m.12 ablation showed no held-out regression and P5.2 repair (h76m.13)
    now owns the ON-arm's repairable vocabulary defects; the deterministic
    _complete_grouped_families safety net (3c2) backstops any residual drop.
    Pass group_candidates=False (--no-group-candidates) to opt out.

    translate_options (bd 2h9j): when True (default) a post-pass bakes
    FieldOption.label_translations for every supported spoken language --
    VERTEX-ONLY with no credential pre-gate (bd f3lm) and fail-open
    (extraction never fails because translation failed; an auth error
    surfaces as a failed report). translation_model overrides the
    OPTION_TRANSLATION_MODEL env default (gemini-2.5-pro)."""
    # 1. Deterministic AcroForm dump (to a temp file unless --keep-dump).
    dump_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    if keep_dump:
        dump_path = os.path.splitext(out_path)[0] + "_acroform.json"
    else:
        fd, dump_path = tempfile.mkstemp(suffix="_acroform.json", dir=dump_dir)
        os.close(fd)
    try:
        acroform_dump.main(["--json", dump_path, pdf_path])

        # 2. The strong-LLM pass over dump + PDF.
        schema = arm_llm_native.run(pdf_path, dump_path, model, send_pdf=True,
                                    plain=plain,
                                    group_candidates=group_candidates)

        # 3. Deterministically back-fill pdf_position from the dump (the LLM is
        #    flaky at coordinates; the dump has them keyed by exact widget name).
        positions_filled = _backfill_positions(schema, dump_path)

        # 3a. Deterministically populate help.instructions from each field's /TU
        #     tooltip (free baseline -- extraction otherwise leaves it blank). Runs
        #     while the dump still exists (it is removed in the finally below).
        instructions_filled = _extract_instructions_from_dump(schema, dump_path)
        # Keep the /TU map for the guidance-enrichment stage (3g): it seeds
        # source-tu provenance so a fresh draft's /TU baseline is machine-
        # owned (upgradeable), not mistaken for human text. Built here while
        # the dump file still exists (removed in the finally below).
        name_to_tu = _build_name_to_tu(dump_path)

        # 3c2. Complete any partially-grouped widget family: when the LLM
        #      consolidated SOME-but-not-all of a mined family into one field's
        #      options[], append the missing members as options of that SAME field
        #      (bd polyglot-pdf-qmxb) -- never retyping it. Runs BEFORE the backfill
        #      so a completed member is not also minted as a loose duplicate.
        group_completion = _complete_grouped_families(schema, dump_path)

        # 3d. Deterministically backfill any fillable dump widget NO field claims
        #     (bd polyglot-pdf-w0eq, P6.1c). The LLM pass stochastically omits a
        #     field (repeat extractions of the same W-7 PDF each drop a
        #     different widget); this guarantees every widget is covered instead
        #     of trusting the model to enumerate all of them.
        widgets_backfilled = _backfill_unclaimed_widgets(schema, dump_path)

        # Keep the dump IN MEMORY for the lint pass at step 4 (the temp file is
        # removed in the finally below; the dump powers the widget-claim rule).
        with open(dump_path, encoding="utf-8") as fh:
            dump_data = json.load(fh)
    finally:
        if not keep_dump and os.path.exists(dump_path):
            os.remove(dump_path)

    # 3e. Deterministic form divisions (bd polyglot-pdf-6cfu.2): derive parts/
    #     sections from the PDF itself (widget-name conventions -> printed
    #     headings -> page fallback) and OVERWRITE whatever the LLM emitted --
    #     stored boundaries are 100% derivation output, never LLM-decided (the
    #     contract no longer asks for sections, and this overwrite guarantees
    #     it either way). Runs after every field exists (positions backfilled,
    #     families completed, unclaimed widgets recovered) so recovered fields
    #     are filed too; fields that fit no division land in per-page
    #     'To review' sections (well-known sec_to_review id prefix) for a
    #     human to re-file in the editor.
    division = derive_sections.derive_and_apply(schema, pdf_path,
                                                cap=division_cap)

    # 3b. Deterministically recover real version metadata (edition/rev, OMB,
    #     expiration) from the PDF and merge it in BEFORE normalize, so real values
    #     win and normalize only fills genuinely-absent scalars (bd s4dp.2).
    doc = fitz.open(pdf_path)
    try:
        version_meta = _extract_version_metadata_from_doc(doc)
    finally:
        doc.close()
    meta = schema.setdefault("form_metadata", {})
    # Do NOT let the "unknown" no-match sentinel overwrite a real version the LLM
    # pass already placed (a valid-but-unsupported revision format) -- only the
    # deterministic recovery should win, never the absence of one (Codex PR #263
    # r2). Same guard for version_confidence (paired with version).
    if version_meta.get("version") == "unknown" and meta.get("version") not in (None, "", "draft", "unknown"):
        version_meta = {k: v for k, v in version_meta.items()
                        if k not in ("version", "version_confidence")}
    meta.update(version_meta)

    # (The old 3c naive instructions-PDF substring enrichment now lives
    #  INSIDE the 3g guidance stage as its unavailable-fallback -- bd wsao.6.)

    # 4. Normalize required-but-missing scalars to draft defaults, REPAIR (bd
    #    h76m.13: deterministic invented-vocabulary rewrites; the report rides
    #    in provenance), then validate + lint (bd h76m.5). main() maps
    #    (schema_valid, lint errors, field count) to the tri-state exit code
    #    (bd v96b: 0 valid+clean / 3 stored-with-issues / 1 no usable draft).
    _normalize_for_schema(schema)
    schema, repair_report = _repair_schema(schema, dump_data)

    # 4b. Post-backfill coverage ledger (bd polyglot-pdf-l1a9): every fillable
    #     dump widget must be claimed by SOME field/option. Backfill (3d) claims
    #     everything the LLM missed, so anything unclaimed HERE means the
    #     pipeline itself failed -- loud stderr + provenance record; the
    #     tri-state exit classifies the draft as ISSUES (never a silent ship).
    unclaimed_fillable = _check_dump_coverage(schema, dump_data)
    if unclaimed_fillable:
        print("COVERAGE-FAILED: fillable widgets claimed by no field: "
              + "; ".join(unclaimed_fillable[:10]), file=sys.stderr)

    # 3f. Bake option label_translations for the supported spoken languages
    #     (bd polyglot-pdf-2h9j). After repair so translations key off the
    #     final labels, before validate/lint so the validated artifact is the
    #     shipped artifact. Fail-open, VERTEX-ONLY with NO credential pre-gate
    #     (bd f3lm -- it always attempts Vertex and fails open on an auth
    #     error); --no-translate-options skips it for cheap extraction runs.
    translation_report = (_bake_option_translations(schema, translation_model)
                          if translate_options else {"skipped": "disabled"})

    # 3g. Guidance enrichment (bd wsao.6; sprint-16): booklet-grounded
    #     help.instructions/details + form-level details, judged + verified,
    #     applied under the provenance guard. After repair (channels key off
    #     final fields), before validate/lint (the shipped artifact is the
    #     linted artifact). Fail-open + fallback (see the helper);
    #     --no-enrich-guidance skips it for cheap extraction-strategy runs.
    guidance_report = (_enrich_guidance(schema, pdf_path, instructions_pdf,
                                        name_to_tu, guidance_model)
                       if enrich_guidance else {"skipped": "disabled"})
    instructions_enriched = guidance_report.get("fallback_enriched", 0)

    # 4c. Extraction provenance (bd polyglot-pdf-l1a9): stamped BEFORE validate
    #     so the validated artifact is the stored artifact -- absence of this
    #     stanza is exactly what 422'd every kit at the publish gate.
    _stamp_extraction_info(schema)

    ok, detail = _validate_schema(schema)
    lint_report = _lint_schema(schema, dump_data)
    schema.setdefault("_bakeoff", {})["authoring"] = {
        "tool": "extract_form.py", "prompt": "plain" if plain else "enriched",
        # positions_filled stays the historical int (field-level count); the
        # option-level pass (bd 5f41) reports its own keys alongside.
        "positions_filled": positions_filled["fields_filled"],
        "option_positions_filled": positions_filled["options_filled"],
        "option_positions_unmatched": positions_filled["unmatched"],
        "instructions_filled": instructions_filled,
        "instructions_enriched": instructions_enriched,
        "group_completion": group_completion,
        "widgets_backfilled": widgets_backfilled,
        # Post-backfill coverage ledger (bd l1a9): [] on a healthy run; any
        # entry is a pipeline failure the exit code surfaces as ISSUES.
        "coverage": {"unclaimed_fillable": unclaimed_fillable},
        # The derived-division record (bd 6cfu.2): strategy + cap actually
        # used, and the 'To review' section/field ids the editor gates on.
        "division": division,
        "schema_valid": ok, "validation": detail,
        "repair": repair_report,
        "lint": lint_report,
        "option_translation": translation_report,
        "instructions_enrich": guidance_report,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2)

    nf = len(schema.get("fields", []))
    status = "OK" if ok else "INVALID"
    instr_note = f", help.instructions: {instructions_filled} from /TU"
    if instructions_enriched:
        # only the NAIVE FALLBACK count (the LLM guidance stage prints its
        # own line below) -- printing it unconditionally misread as "the
        # booklet added nothing" on the happy path (wsao.6 fresh-eyes)
        instr_note += (f" + {instructions_enriched} via naive booklet "
                       f"fallback")
    print(f"[{status}] wrote {out_path} -- {nf} fields, prompt="
          f"{'plain' if plain else 'enriched'}{instr_note}; {detail}")
    print(f"division: {division['strategy']} -- {division['parts']} part(s) / "
          f"{division['sections']} section(s), cap {division['cap']}"
          + (f", {len(division['to_review_field_ids'])} field(s) in "
             f"'To review' for human re-filing"
             if division["to_review_field_ids"] else ""))
    if repair_report.get("skipped"):
        print(f"repair: skipped ({repair_report['skipped']})", file=sys.stderr)
    elif repair_report.get("failed"):
        print(f"repair: FAILED ({repair_report['failed']})", file=sys.stderr)
    else:
        print(f"repair: {repair_report['applied']} applied, "
              f"{repair_report['dropped']} dropped-with-error, "
              f"alias hits: {repair_report['alias_hits']}")
    if translation_report.get("skipped"):
        print(f"option translations: skipped ({translation_report['skipped']})")
    elif translation_report.get("failed"):
        print(f"option translations: FAILED ({translation_report['failed']}) "
              "-- run scripts/authoring/translate_option_labels.py to bake "
              "them later", file=sys.stderr)
    else:
        langs = translation_report.get("languages", {})
        updated = sum(e.get("options_updated", 0) for e in langs.values())
        # Field spoken names ride the same bake (bd polyglot-pdf-tupu.1).
        names_updated = sum(e.get("fields_updated", 0) for e in langs.values())
        failed = translation_report.get("failed_languages") or []
        print(f"option translations: {updated} option-language entries + "
              f"{names_updated} spoken-name entries across "
              f"{len(langs)} language(s), model {translation_report.get('model')}"
              + (f"; FAILED: {', '.join(failed)} -- re-run "
                 "translate_option_labels.py to fill the gap" if failed else ""))
        flag_line = _translation_flag_summary(translation_report)
        if flag_line:
            print(flag_line)
    if guidance_report.get("skipped"):
        _fb = guidance_report.get("fallback_enriched", 0)
        print(f"guidance: skipped ({guidance_report['skipped']})"
              + (f" -- naive fallback enriched {_fb} field(s)"
                 if _fb else ""),
              file=sys.stderr)
    elif guidance_report.get("failed"):
        print(f"guidance: FAILED ({guidance_report['failed']}) -- naive "
              f"fallback enriched {guidance_report.get('fallback_enriched', 0)}"
              f" field(s)", file=sys.stderr)
    elif guidance_report.get("unavailable"):
        print("guidance: JUDGE UNAVAILABLE (the Vertex judge call failed -- "
              "check ADC / GOOGLE_CLOUD_PROJECT for the polyglot-demo "
              "project, or pass --no-enrich-guidance) -- authored guidance "
              "dropped per the KEEP rule; naive fallback enriched "
              f"{guidance_report.get('fallback_enriched', 0)} field(s)",
              file=sys.stderr)
    else:
        gflags = guidance_report.get("flags") or []
        gunmatched = guidance_report.get("unmatched_proposal_ids") or []
        print(f"guidance: {guidance_report.get('written', 0)} field(s) "
              f"enriched, {guidance_report.get('skipped_human', 0)} "
              f"human-owned skipped, {len(gflags)} flag(s)"
              + (" -- recorded in _bakeoff.authoring.instructions_enrich"
                 ".flags (WARNINGs, human-review worklist)" if gflags else "")
              + (f"; {len(gunmatched)} proposal(s) matched NO schema field "
                 f"and were discarded: {gunmatched[:5]}" if gunmatched else ""))
    if lint_report.get("skipped"):
        print(f"lint: skipped ({lint_report['skipped']})", file=sys.stderr)
    else:
        print(f"lint: {lint_report['errors']} error(s), "
              f"{lint_report['warnings']} warning(s)"
              + (" -- findings recorded in _bakeoff.authoring.lint"
                 if lint_report["findings"] else ""))
        for finding in lint_report["findings"][:10]:
            print(f"  {finding['severity']} [{finding['rule']}] "
                  f"{finding['path']}: {finding['message']}")
        if len(lint_report["findings"]) > 10:
            print(f"  ... and {len(lint_report['findings']) - 10} more (see the draft)")
    if not ok:
        print("WARNING: the draft did not validate; inspect before editing.",
              file=sys.stderr)
    return schema


# Tri-state exit codes (bd polyglot-pdf-v96b, P5.3a). The hosted extract route
# reads these to decide store-with-issues (3) vs hard-fail (1):
#   0  VALID     -- draft validated AND lint-clean; ready to promote.
#   3  ISSUES    -- a usable draft was written (>= 1 field) but it is invalid
#                   and/or carries lint ERRORs: STORE it with its issue report.
#   1  HARD_FAIL -- no usable draft (0 fields); the caller must NOT store it.
# A crash before the write (no draft at all) surfaces as a raised exception ->
# nonzero via the traceback, which the route also treats as hard-fail.
EXIT_VALID = 0
EXIT_ISSUES = 3
EXIT_HARD_FAIL = 1


def _classify_exit(schema: dict) -> int:
    """Tri-state exit code for a written draft (see EXIT_* above)."""
    fields = schema.get("fields")
    # "Usable" means >= 1 FIELD-SHAPED (dict) member -- a list of non-dict junk
    # is no more usable than an empty list (it lints to 0 findings), and the
    # hosted route applies the same dict-member floor (fresh-eyes, bd v96b).
    if not isinstance(fields, list) or not any(isinstance(f, dict) for f in fields):
        return EXIT_HARD_FAIL  # nothing usable was produced
    authoring = schema.get("_bakeoff", {}).get("authoring", {})
    valid = bool(authoring.get("schema_valid"))
    lint = authoring.get("lint") or {}
    lint_errors = lint.get("errors", 0) or 0
    # A failed repair (RepairError degraded to a report -- e.g. hallucinated
    # widgets, no-name fields) or a post-backfill coverage failure is an ISSUES
    # draft even when Pydantic validates and lint shows no ERROR -- both were
    # previously invisible to this classification, so a draft that failed
    # repair could exit 0 VALID (bd polyglot-pdf-l1a9).
    repair_failed = bool((authoring.get("repair") or {}).get("failed"))
    coverage_gap = bool(
        ((authoring.get("coverage") or {}).get("unclaimed_fillable")) or []
    )
    if valid and lint_errors == 0 and not repair_failed and not coverage_gap:
        return EXIT_VALID
    return EXIT_ISSUES


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="One-command PDF -> draft FormSchema (bd 7a9.12 / B1).")
    ap.add_argument("--pdf", required=True, help="the fillable form PDF")
    ap.add_argument("--out", required=True, help="output draft schema.json path")
    ap.add_argument("--model", default="claude-opus-5",
                    help="extractor model (claude-* local CLI free in-env; DEFAULT)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--plain", dest="plain", action="store_true", default=None,
                     help="force the plain claude-hybrid prompt")
    grp.add_argument("--enriched", dest="plain", action="store_false",
                     help="force the enriched-bundle prompt")
    ap.add_argument("--keep-dump", action="store_true",
                    help="keep the intermediate AcroForm dump (<out>_acroform.json)")
    ap.add_argument("--no-group-candidates", dest="group_candidates",
                    action="store_false", default=True,
                    help="OPT OUT of the deterministic pre-grouping candidates "
                         "block (bd h76m.12; default ON per bd qmxb)")
    ap.add_argument("--instructions-pdf", default=None,
                    help="OPTIONAL official instructions PDF: the primary "
                         "source for the LLM guidance stage (bd wsao.6; a "
                         "booklet next to the form PDF is auto-discovered "
                         "without this flag), and the input to the naive "
                         "substring fallback (bd s4dp.3) when that stage is "
                         "unavailable")
    ap.add_argument("--division-cap", type=int,
                    default=derive_sections.DEFAULT_CAP,
                    help="display-sanity cap on fields per derived section "
                         f"(bd 6cfu.2; default {derive_sections.DEFAULT_CAP}, "
                         "splits are balanced)")
    ap.add_argument("--no-translate-options", dest="translate_options",
                    action="store_false", default=True,
                    help="skip baking option label_translations (bd 2h9j; "
                         "default ON, Vertex-only + fail-open, no credential "
                         "pre-gate -- turn off for cheap extraction-strategy "
                         "test runs)")
    ap.add_argument("--translation-model", default=None,
                    help="Gemini model for the option-translation bake "
                         "(default: OPTION_TRANSLATION_MODEL env or "
                         "gemini-2.5-pro)")
    ap.add_argument("--no-enrich-guidance", dest="enrich_guidance",
                    action="store_false", default=True,
                    help="skip the booklet-grounded guidance enrichment "
                         "stage (bd wsao.6; default ON, fail-open, needs an "
                         "instructions booklet next to the PDF or "
                         "--instructions-pdf -- turn off for cheap "
                         "extraction-strategy test runs)")
    ap.add_argument("--guidance-model", default=None,
                    help="authoring model for the guidance enrichment stage "
                         "(default: INSTRUCTIONS_MODEL env, then "
                         "EXTRACTOR_MODEL env, then the local claude CLI)")
    args = ap.parse_args(argv)

    plain = DEFAULT_PLAIN if args.plain is None else args.plain
    schema = extract(args.pdf, args.out, plain=plain, model=args.model,
                     keep_dump=args.keep_dump,
                     instructions_pdf=args.instructions_pdf,
                     group_candidates=args.group_candidates,
                     division_cap=args.division_cap,
                     translate_options=args.translate_options,
                     translation_model=args.translation_model,
                     enrich_guidance=args.enrich_guidance,
                     guidance_model=args.guidance_model)
    # Tri-state exit (bd v96b): 0 valid+clean / 3 stored-with-issues / 1 no
    # usable draft. The draft was already written unconditionally in extract().
    return _classify_exit(schema)


if __name__ == "__main__":
    sys.exit(main())
