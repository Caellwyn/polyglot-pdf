"""Guidance-enrichment engine, DRY-RUN ONLY (bd polyglot-pdf-wsao.4).

Reads a form kit's schema + its official instructions booklet and asks an LLM
to author the sprint-16 guidance channels for every askable field:

  - help.instructions  -- 2-4 sentence spoken overview (abstractive),
  - help.details       -- VERBATIM booklet excerpts, selected up to the 20k
                          inline budget + a one-line index of dropped topics
                          (the wsao.8 selection+index policy; NEVER summarize),
  - help.format_hint   -- short input-format hint when the sources give one,
  plus ONE form-level details block (eligibility / documents / where-to-apply
  content that attaches to no field).

The content rules come VERBATIM from guidance_contract.CONTRACT_TEXT (one
module shared with lint + the wsao.5 judge, so the checks cannot drift from
the prompt). Output is a PROPOSALS JSON + a human diff report -- this bead
NEVER writes a kit; the verify loop + provenance-guarded write is wsao.5.

Booklet text note (wsao.3 table-region eyeball, recorded on that bead): the
prose pages extract cleanly with PyMuPDF; the Exceptions-Tables GRID pages
interleave at row level in every mode. The floor and the excerpts both come
from the SAME extraction here, so containment stays consistent; row
reconstruction / IRS-HTML sourcing for table regions is a known follow-up.

Usage (from the repo root; local Claude CLI is the free default):
    python scripts/authoring/enrich_instructions.py --kit form-kits/w7 \
        [--instructions-pdf form-kits/w7/w7-instructions.pdf] \
        [--model claude-opus-4-8] [--chunk-size 40] \
        [--out scripts/bakeoff/outputs/w7_guidance_proposals.json]

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts", "bakeoff"))

import fitz  # noqa: E402  (PyMuPDF)

from backend.services import guidance_contract  # noqa: E402
from backend.services.schema_lint import lint_schema  # noqa: E402
import llm_providers  # noqa: E402

DEFAULT_MODEL = os.getenv("INSTRUCTIONS_MODEL",
                          os.getenv("EXTRACTOR_MODEL", "claude-opus-4-8"))
DEFAULT_CHUNK = 40


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #

def find_booklet(kit_dir: str, explicit: Optional[str]) -> Optional[str]:
    """--instructions-pdf wins; else glob the kit dir (filenames are
    inconsistent across kits: w7-instructions.pdf, i-90instr.pdf, the editor
    upload's instructions.pdf)."""
    if explicit:
        return explicit
    for pattern in ("instructions.pdf", "*instructions*.pdf", "*instr*.pdf"):
        hits = sorted(glob.glob(os.path.join(kit_dir, pattern)))
        if hits:
            return hits[0]
    return None


def booklet_text(path: str) -> str:
    doc = fitz.open(path)
    try:
        raw = "\n\f\n".join(doc[i].get_text() for i in range(doc.page_count))
    finally:
        doc.close()
    # Strip page furniture (CAUTION!/TIP sidebars, footers) BEFORE the model
    # sees it AND before it becomes the containment floor -- the raw stream
    # interleaves furniture mid-sentence (guidance_contract docstring).
    return guidance_contract.clean_booklet_furniture(raw)


def askable_fields(schema: dict) -> List[dict]:
    return [f for f in schema.get("fields", [])
            if isinstance(f, dict) and not f.get("read_only")
            and f.get("type") != "signature"]


def field_digest(f: dict) -> dict:
    """The compact model-facing view of one field: identification + the
    signals the contract's priority rules need (options for choice framing,
    show_if so modeled conditions are not restated, existing /TU as source)."""
    d: Dict[str, Any] = {"id": f.get("id"), "name": f.get("name"),
                         "type": f.get("type")}
    if f.get("spoken_name"):
        d["spoken_name"] = f["spoken_name"]
    opts = f.get("options")
    if isinstance(opts, list) and opts:
        d["options"] = [{"value": o.get("value"), "label": o.get("label")}
                        for o in opts if isinstance(o, dict)]
    if f.get("show_if"):
        d["show_if"] = f["show_if"]
    help_obj = f.get("help") if isinstance(f.get("help"), dict) else {}
    existing = (help_obj.get("instructions") or "").strip() \
        if isinstance(help_obj.get("instructions"), str) else ""
    if existing:
        d["existing_instructions"] = existing  # usually the /TU tooltip
    return d


# --------------------------------------------------------------------------- #
# Prompting
# --------------------------------------------------------------------------- #

_OUTPUT_SPEC = """
OUTPUT -- one JSON object, nothing else:
{
  "fields": {
    "<field_id>": {
      "instructions": "<2-4 sentences, or \\"\\" when the sources add nothing>",
      "details": "<verbatim booklet excerpts under short headings, or \\"\\">",
      "format_hint": "<short format hint, or omit>"
    }, ...
  },
  "form_details": "<verbatim booklet excerpts for FORM-level guidance
    (eligibility, supporting documents, how/when/where to apply) that
    attaches to no single field, under short headings, or \\"\\">"
}
Cover EVERY field listed in FIELDS below (emit an entry even when both
channels are empty). details/form_details MUST be word-for-word from the
OFFICIAL INSTRUCTIONS TEXT -- a mechanical containment check rejects
anything else. HARD RULES the check enforces:
- Copy CONTIGUOUS passages only. NEVER skip sentences, clauses, or list
  items inside a copied passage -- excerpt a whole numbered/lettered list
  or stop before it. Dropping an item reads as misleading legal advice.
- The check runs PER PARAGRAPH (text between blank lines): one paragraph
  must be ONE unbroken span of the source. Skipping material is allowed
  ONLY at a paragraph break -- end the excerpt, insert a BLANK LINE, and
  start the next excerpt as its own paragraph. Never glue two non-adjacent
  source sentences into one paragraph.
- instructions must never say "see the instructions", "see page N", or
  point at anything on screen -- they are SPOKEN.
- If your instructions would only restate the field's label or options,
  emit "" instead (empty beats filler; a restatement is a lint finding).
Only fields whose booklet coverage is substantial need details; simple
fields (a plain name/date box) usually need only instructions grounded in
their existing tooltip text.
"""


def build_prompt(form_name: str, booklet: str, digests: List[dict]) -> str:
    return (
        guidance_contract.CONTRACT_TEXT
        + "\n\nFORM: " + form_name
        + "\n\nOFFICIAL INSTRUCTIONS TEXT (the ONLY permitted source for "
          "details/form_details; page breaks are form-feeds):\n---\n"
        + booklet
        + "\n---\n\nFIELDS (author guidance for each):\n"
        + json.dumps(digests, ensure_ascii=False, indent=1)
        + "\n" + _OUTPUT_SPEC
    )


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

def enrich(kit_dir: str, instructions_pdf: Optional[str], model: str,
           chunk_size: int) -> dict:
    schema_path = os.path.join(kit_dir, "schema.json")
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    booklet_path = find_booklet(kit_dir, instructions_pdf)
    if not booklet_path:
        raise SystemExit(f"no instructions booklet found in {kit_dir} "
                         f"(pass --instructions-pdf)")
    booklet = booklet_text(booklet_path)
    fields = askable_fields(schema)
    form_name = ((schema.get("form_metadata") or {}).get("title")
                 or os.path.basename(kit_dir))

    runner = llm_providers.resolve_json_runner(model)
    proposals: Dict[str, Any] = {"fields": {}, "form_details": ""}
    tokens: List[dict] = []
    for i in range(0, len(fields), chunk_size):
        chunk = fields[i:i + chunk_size]
        prompt = build_prompt(form_name, booklet,
                              [field_digest(f) for f in chunk])
        obj, tok = runner(prompt, model)
        tokens.append(tok)
        for fid, entry in (obj.get("fields") or {}).items():
            if isinstance(entry, dict):
                proposals["fields"][fid] = entry
        # form_details: keep the longest non-empty candidate across chunks
        # (each chunk sees the whole booklet; the fullest selection wins).
        fd = obj.get("form_details")
        if isinstance(fd, str) and len(fd) > len(proposals["form_details"]):
            proposals["form_details"] = fd

    return {
        "kit": kit_dir,
        "model": model,
        "booklet": booklet_path,
        "booklet_chars": len(booklet),
        "proposals": proposals,
        "tokens": tokens,
    }


def apply_to_copy(schema: dict, proposals: dict, booklet: str) -> dict:
    """Apply proposals to a DEEP COPY of the schema (for lint/diff only --
    this bead never writes a kit)."""
    out = json.loads(json.dumps(schema))
    for f in out.get("fields", []):
        entry = (proposals.get("fields") or {}).get(f.get("id"))
        if not isinstance(entry, dict):
            continue
        help_obj = f.get("help") if isinstance(f.get("help"), dict) else {}
        for key in ("instructions", "details", "format_hint"):
            val = entry.get(key)
            if isinstance(val, str) and val.strip():
                help_obj[key] = val.strip()
        if help_obj:
            f["help"] = help_obj
    meta = out.setdefault("form_metadata", {})
    fd = proposals.get("form_details")
    if isinstance(fd, str) and fd.strip():
        meta["details"] = fd.strip()
    meta["booklet_text"] = booklet
    return out


def report(result: dict, schema: dict) -> dict:
    """Coverage + lint verdict over the proposals (the bead's exit gates)."""
    proposals = result["proposals"]
    booklet = booklet_text(result["booklet"])
    fields = askable_fields(schema)
    covered = [f for f in fields
               if ((proposals["fields"].get(f.get("id")) or {})
                   .get("instructions") or "").strip()]
    applied = apply_to_copy(schema, proposals, booklet)
    findings = [fnd.as_dict() for fnd in lint_schema(applied)
                if fnd.rule.startswith("help-")]
    return {
        "askable": len(fields),
        "instructions_covered": len(covered),
        "coverage_pct": round(100.0 * len(covered) / len(fields), 1)
                        if fields else None,
        "details_fields": sum(
            1 for e in proposals["fields"].values()
            if (e.get("details") or "").strip()),
        "form_details_chars": len(proposals.get("form_details") or ""),
        "guidance_findings": findings,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kit", required=True, help="form-kits/<id> directory")
    ap.add_argument("--instructions-pdf")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK)
    ap.add_argument("--out", help="proposals JSON path (default: "
                                  "scripts/bakeoff/outputs/<kit>_guidance_proposals.json)")
    args = ap.parse_args(argv)

    result = enrich(args.kit, args.instructions_pdf, args.model,
                    args.chunk_size)
    with open(os.path.join(args.kit, "schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    rep = report(result, schema)
    result["report"] = rep

    out = args.out or os.path.join(
        _REPO, "scripts", "bakeoff", "outputs",
        os.path.basename(os.path.normpath(args.kit))
        + "_guidance_proposals.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    print(f"proposals: {out}")
    print(f"coverage: {rep['instructions_covered']}/{rep['askable']} "
          f"({rep['coverage_pct']}%) | details on {rep['details_fields']} "
          f"fields | form_details {rep['form_details_chars']} chars")
    print(f"guidance lint findings: {len(rep['guidance_findings'])}")
    for f in rep["guidance_findings"][:10]:
        print(f"  [{f['severity']}] {f['rule']} @ {f['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
