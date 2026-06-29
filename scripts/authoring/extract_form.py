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

import fitz  # PyMuPDF -- page-1 text + doc.metadata for version extraction.

# Reuse the bakeoff machinery (the bead: "reuse the validated scripts/bakeoff/").
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))
import acroform_dump  # noqa: E402
import arm_llm_native  # noqa: E402

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


def _backfill_positions(schema: dict, dump_path: str) -> int:
    """Deterministically set `pdf_position` on each field from the AcroForm dump.

    The LLM is flaky at copying widget coordinates (the B1 bake measured pos 0%
    on both arms), but the dump HAS every widget's rect keyed by its exact name,
    and the draft copies that name verbatim into `pdf_field_name`. So we fill
    pdf_position from the dump for free -- a deterministic gain over either raw
    arm. Returns the number of fields filled. Dump rects are 0-based pages; the
    gold/schema convention is 1-based, so we +1."""
    try:
        with open(dump_path, encoding="utf-8") as fh:
            dump = json.load(fh)
    except OSError:
        return 0
    name_to_rect: dict[str, dict] = {}
    for f in dump.get("fields", []):
        for w in f.get("widgets", []):
            r = w.get("rect")
            if r and f.get("name") and f["name"] not in name_to_rect:
                name_to_rect[f["name"]] = r

    def rect_to_pos(r: dict) -> dict:
        return {"page": int(r["page"]) + 1, "x": r["x"], "y": r["y"],
                "width": r["width"], "height": r["height"]}

    filled = 0
    for field in schema.get("fields", []):
        # Back-fill when the position is MISSING *or* DEGENERATE. The LLM often
        # emits a placeholder {page, x:0, y:0, width:0, height:0} -- a truthy dict
        # that a bare `if field.get("pdf_position")` would treat as already set,
        # leaving the zeros in place (the editor then can't map the field to the
        # PDF, so click-to-jump dies -- bd 7a9.18). A real widget always has a
        # positive width AND height, so a non-positive either means it needs the
        # deterministic dump rect.
        if _has_usable_position(field.get("pdf_position")):
            continue
        # A field's position = the rect of its (first) pdf_field_name; for a
        # consolidated options[] field, use the first option's widget.
        pfn = field.get("pdf_field_name")
        if not pfn:
            for o in (field.get("options") or []):
                if o.get("pdf_field_name"):
                    pfn = o["pdf_field_name"]
                    break
        rect = name_to_rect.get(pfn) if pfn else None
        if rect:
            field["pdf_position"] = rect_to_pos(rect)
            filled += 1
    return filled


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


def extract(pdf_path: str, out_path: str, *, plain: bool = DEFAULT_PLAIN,
            model: str = "claude-opus-4-8", keep_dump: bool = False) -> dict:
    """Run the full PDF -> draft-schema pass and write `out_path`. Returns the
    draft dict (with a `_bakeoff` provenance block)."""
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
                                    plain=plain)

        # 3. Deterministically back-fill pdf_position from the dump (the LLM is
        #    flaky at coordinates; the dump has them keyed by exact widget name).
        positions_filled = _backfill_positions(schema, dump_path)
    finally:
        if not keep_dump and os.path.exists(dump_path):
            os.remove(dump_path)

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

    # 4. Normalize required-but-missing scalars to draft defaults, then validate.
    _normalize_for_schema(schema)
    ok, detail = _validate_schema(schema)
    schema.setdefault("_bakeoff", {})["authoring"] = {
        "tool": "extract_form.py", "prompt": "plain" if plain else "enriched",
        "positions_filled": positions_filled,
        "schema_valid": ok, "validation": detail,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2)

    nf = len(schema.get("fields", []))
    status = "OK" if ok else "INVALID"
    print(f"[{status}] wrote {out_path} -- {nf} fields, prompt="
          f"{'plain' if plain else 'enriched'}; {detail}")
    if not ok:
        print("WARNING: the draft did not validate; inspect before editing.",
              file=sys.stderr)
    return schema


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="One-command PDF -> draft FormSchema (bd 7a9.12 / B1).")
    ap.add_argument("--pdf", required=True, help="the fillable form PDF")
    ap.add_argument("--out", required=True, help="output draft schema.json path")
    ap.add_argument("--model", default="claude-opus-4-8",
                    help="extractor model (claude-* local CLI free in-env; DEFAULT)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--plain", dest="plain", action="store_true", default=None,
                     help="force the plain claude-hybrid prompt")
    grp.add_argument("--enriched", dest="plain", action="store_false",
                     help="force the enriched-bundle prompt")
    ap.add_argument("--keep-dump", action="store_true",
                    help="keep the intermediate AcroForm dump (<out>_acroform.json)")
    args = ap.parse_args(argv)

    plain = DEFAULT_PLAIN if args.plain is None else args.plain
    schema = extract(args.pdf, args.out, plain=plain, model=args.model,
                     keep_dump=args.keep_dump)
    return 0 if schema.get("_bakeoff", {}).get("authoring", {}).get("schema_valid") else 1


if __name__ == "__main__":
    sys.exit(main())
