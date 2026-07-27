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
import re
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
- EVERY rule above applies to form_details IDENTICALLY -- it is checked by
  the same per-paragraph containment gate as field details.
Only fields whose booklet coverage is substantial need details; simple
fields (a plain name/date box) usually need only instructions grounded in
their existing tooltip text.
"""


def build_prompt(form_name: str, booklet: str, digests: List[dict]) -> str:
    # TRUST ASSUMPTION (wsao.4 outer review): the booklet text is interpolated
    # RAW between the --- fences (digests are JSON-encoded). The booklet is a
    # trusted artifact (an official IRS/USCIS publication committed to the
    # kit), not user input -- a hostile booklet could steer the prompt, so
    # never point this engine at an untrusted PDF.
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
# Deterministic contiguity repair (bd wsao.4 outer review). The one recurring
# model slip is gluing NON-ADJACENT verbatim passages into a single paragraph
# (a skipped Note/list block mid-paragraph). That is a FORMATTING defect over
# verbatim content, so it is mechanically repairable: split the paragraph at
# the longest contained-prefix boundary and re-check both halves. A fragment
# that stays uncontained after splitting is genuinely non-verbatim -> DROP it
# and record it (select-not-rewrite: dropping is always safe; rewriting never
# is). Deterministic, so re-runnable over an existing proposals artifact.
# --------------------------------------------------------------------------- #

def _longest_contained_prefix(norm_para: str, booklet_norm: str) -> int:
    lo, hi = 0, len(norm_para)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if booklet_norm.find(norm_para[:mid]) >= 0:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _first_sentence_split(text: str) -> tuple[str, str]:
    """(first sentence-ish unit, rest). Falls back to the whole text."""
    m = min((i for i in (text.find(". "), text.find(".\n"), text.find("; "))
             if i >= 0), default=-1)
    if m < 0:
        return text, ""
    return text[:m + 1], text[m + 1:].strip()


def _repair_span(span: str, booklet_norm: str) -> tuple[List[str], List[str]]:
    """Repair ONE body span: emit contained pieces (split at contained-prefix
    boundaries), drop non-verbatim SENTENCES (not the whole span -- an
    interleaved [verbatim A][paraphrase B][verbatim C] keeps A and C; bd
    polyglot-pdf-9v3p). Every emitted piece is containment-verified."""
    pieces: List[str] = []
    drops: List[str] = []
    remainder = span.strip()
    guard = 0
    while remainder and guard < 60:
        guard += 1
        if guidance_contract.check_containment_normalized(
                remainder, booklet_norm).contained:
            pieces.append(remainder)
            return pieces, drops
        norm = guidance_contract.normalize_for_containment(remainder)
        cut_norm = _longest_contained_prefix(norm, booklet_norm)
        if cut_norm < 24:
            # the span STARTS with non-verbatim text: drop its first
            # sentence and keep repairing the rest (never the whole span)
            head, rest = _first_sentence_split(remainder)
            drops.append(head[:120])
            remainder = rest
            continue
        # map the normalized cut back to raw text, back up to a sentence end
        raw_cut = None
        for i in range(len(remainder), 0, -1):
            if len(guidance_contract.normalize_for_containment(
                    remainder[:i])) <= cut_norm:
                raw_cut = i
                break
        if not raw_cut:
            head, rest = _first_sentence_split(remainder)
            drops.append(head[:120])
            remainder = rest
            continue
        head = remainder[:raw_cut]
        m = max(head.rfind(". "), head.rfind(".\n"), head.rfind(";"))
        if m > 24:
            head, rest = remainder[:m + 1], remainder[m + 1:]
        else:
            rest = remainder[raw_cut:]
        head = head.strip()
        if head and guidance_contract.check_containment_normalized(
                head, booklet_norm).contained:
            pieces.append(head)
            remainder = rest.strip()
        else:
            # contained-prefix mapping failed cleanly: drop one sentence
            drop_head, rest2 = _first_sentence_split(remainder)
            drops.append(drop_head[:120])
            remainder = rest2
    if remainder:
        drops.append(remainder[:120])
    return pieces, drops


def repair_details_contiguity(details: str, booklet_norm: str) -> tuple[str, List[str]]:
    """Split glued paragraphs at contained-prefix boundaries; drop residues
    that remain non-verbatim (sentence-granular -- see _repair_span). Returns
    (repaired_details, dropped_fragments). Iterates EVERY body segment using
    the SAME blank-line regex as the containment checker (a whitespace-bearing
    blank line like '\\n \\n' previously lost segments silently -- wsao.4
    outer review)."""
    out_paras: List[str] = []
    dropped: List[str] = []
    for raw in re.split(r"\n\s*\n", details or ""):
        para = raw.strip()
        if not para:
            continue
        lines = para.splitlines()
        heading_lines = [ln for ln in lines
                         if guidance_contract.has_heading(ln)
                         and len(ln) <= 120]
        body_text = "\n".join(ln for ln in lines
                              if ln not in heading_lines).strip()
        if not body_text:  # heading-only scaffolding
            out_paras.append(para)
            continue
        pieces, drops = _repair_span(body_text, booklet_norm)
        dropped.extend(drops)
        if heading_lines and pieces:
            pieces[0] = "\n".join(heading_lines) + "\n" + pieces[0]
        out_paras.extend(pieces)
    return "\n\n".join(out_paras), dropped


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

    # Deterministic contiguity repair over BOTH channels (see the repairer's
    # rationale above): splits glued verbatim passages, drops paraphrase.
    booklet_norm = guidance_contract.normalize_for_containment(booklet)
    dropped_report: Dict[str, List[str]] = {}
    for fid, entry in proposals["fields"].items():
        det = entry.get("details")
        if isinstance(det, str) and det.strip():
            repaired, dropped = repair_details_contiguity(det, booklet_norm)
            entry["details"] = repaired
            if dropped:
                dropped_report[fid] = dropped
    if proposals["form_details"].strip():
        repaired, dropped = repair_details_contiguity(
            proposals["form_details"], booklet_norm)
        proposals["form_details"] = repaired
        if dropped:
            dropped_report["<form_details>"] = dropped

    return {
        "contiguity_dropped": dropped_report,
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
    ap.add_argument("--from-proposals",
                    help="skip authoring; load an existing proposals JSON "
                         "(e.g. the committed wsao.4 artifact) and run the "
                         "verify/write stages over it")
    ap.add_argument("--verify", action="store_true",
                    help="run the judge + bounded rectify loop (bd wsao.5)")
    ap.add_argument("--write", action="store_true",
                    help="provenance-guarded write to the kit schema.json "
                         "(implies --verify: never write unverified text)")
    ap.add_argument("--bootstrap-provenance", action="store_true",
                    help="legacy-kit one-time pass: mark fields whose current "
                         "instructions EXACTLY match their /TU tooltip as "
                         "machine-owned (source: tu) and persist the "
                         "provenance block; NO content changes")
    args = ap.parse_args(argv)

    if args.bootstrap_provenance:
        schema_path = os.path.join(args.kit, "schema.json")
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
        tu = tu_map_from_pdf(os.path.join(args.kit, "form.pdf"))
        prov = bootstrap_provenance(schema, tu)
        bakeoff = schema.setdefault("_bakeoff", {}).setdefault("authoring", {})
        enrich_block = bakeoff.setdefault("instructions_enrich", {})
        merged = dict(enrich_block.get("provenance") or {})
        merged.update(prov)
        enrich_block["provenance"] = merged
        with open(schema_path, "w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2, ensure_ascii=False)
        total = sum(1 for f in schema.get("fields", [])
                    if isinstance(f, dict)
                    and isinstance(f.get("help"), dict)
                    and (f["help"].get("instructions") or "").strip())
        print(f"bootstrap: {len(prov)} of {total} instruction-bearing fields "
              f"marked machine-owned (source: tu); the rest stay "
              f"human-protected")
        return 0

    if args.from_proposals:
        with open(args.from_proposals, encoding="utf-8") as fh:
            result = json.load(fh)
    else:
        result = enrich(args.kit, args.instructions_pdf, args.model,
                        args.chunk_size)
    with open(os.path.join(args.kit, "schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)

    flags: List[dict] = []
    booklet = booklet_text(result["booklet"]) \
        if (args.verify or args.write) else ""
    if args.verify or args.write:
        form_name = ((schema.get("form_metadata") or {}).get("title")
                     or os.path.basename(args.kit))
        flags = verify_and_rectify(schema, result["proposals"], booklet,
                                   form_name, args.model)
        result["verify_flags"] = flags
        print(f"verify: {len(flags)} flag(s): "
              f"{[f['rule'] for f in flags][:6]}")

    rep = report(result, schema)
    result["report"] = rep

    if args.write:
        summary = write_kit(args.kit, result["proposals"], booklet, flags,
                            args.model, JUDGE_MODEL)
        result["write_summary"] = summary
        print(f"write: {summary['written']} field(s) written, "
              f"{summary['skipped_human']} human-owned skipped, "
              f"{summary['flags']} flag(s) persisted")

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


# (the __main__ guard lives at the END of the file so
# every appended definition exists before main() runs)


# --------------------------------------------------------------------------- #
# Verify loop + provenance-guarded write (bd wsao.5). Mirrors the translation
# bake's shape: chunked judge (flash-lite tier) -> bounded rectify (max 2,
# full re-entry) -> KEEP rule (unresolved/unavailable falls back to the
# deterministic baseline -- never ship unverified LLM legal text). Flags
# persist at _bakeoff.authoring.instructions_enrich.flags; schema_lint
# re-emits them (GUIDANCE_FLAG_RULES) so the editor worklist is free.
# --------------------------------------------------------------------------- #

import hashlib

# Mid-tier judge (wsao.5 measured): flash-lite mass-failed genuine guidance
# on `useful_beyond_label` (22 false-negative drops on the w7 set, e.g.
# treaty_country's grounded residence-country interlock judged "not useful").
# Judgment quality needs the mid tier; run_json_gemini pins the thinking
# budget so the Vertex flash default cannot blow the cost up.
JUDGE_MODEL = os.getenv("GUIDANCE_JUDGE_MODEL", "gemini-2.5-flash")
JUDGE_CHUNK = 50
RECTIFY_MAX_ROUNDS = 2


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _judge_prompt(form_name: str, booklet: str, entries: List[dict]) -> str:
    spec = ('{"fields": {"<field_id>": {"grounded": bool, '
            '"unsupported_claims": [], "useful_beyond_label": bool, '
            '"omission_concerns": [], "advice": bool}, ...}}')
    return (guidance_contract.JUDGE_TEXT
            + "\n\nFORM: " + form_name
            + "\n\nOFFICIAL INSTRUCTIONS TEXT:\n---\n" + booklet + "\n---\n"
            + "\nFIELDS UNDER JUDGMENT (digest + authored guidance):\n"
            + json.dumps(entries, ensure_ascii=False, indent=1)
            + "\n\nOUTPUT -- one JSON object, nothing else:\n" + spec
            + "\nCover every field listed.")


def _passes(verdict: dict) -> bool:
    return bool(verdict.get("grounded")) \
        and not verdict.get("advice") \
        and not verdict.get("omission_concerns") \
        and (bool(verdict.get("useful_beyond_label"))
             or not verdict.get("_has_instructions", True))


def judge_proposals(schema: dict, proposals: dict, booklet: str,
                    form_name: str, model: str = JUDGE_MODEL) -> dict:
    """Run the judge over every field with authored guidance. Returns
    {field_id: verdict}. Raises on transport failure (caller applies the
    unavailable KEEP rule)."""
    fields_by_id = {f.get("id"): f for f in schema.get("fields", [])
                    if isinstance(f, dict)}
    entries = []
    for fid, e in (proposals.get("fields") or {}).items():
        instr = (e.get("instructions") or "").strip()
        det = (e.get("details") or "").strip()
        # format_hint is judged too: write_kit stamps it llm-verified, so a
        # format_hint-only field skipping the judge would be the same
        # fail-open class as judge-omission (wsao.5 fresh-eyes round 2)
        fh = (e.get("format_hint") or "").strip()
        if not instr and not det and not fh:
            continue
        digest = field_digest(fields_by_id.get(fid) or {"id": fid})
        entry = {"digest": digest, "instructions": instr, "details": det}
        if fh:
            entry["format_hint"] = fh
        entries.append(entry)
    runner = llm_providers.resolve_json_runner(model)
    verdicts: Dict[str, dict] = {}
    for i in range(0, len(entries), JUDGE_CHUNK):
        chunk = entries[i:i + JUDGE_CHUNK]
        obj, _tok = runner(_judge_prompt(form_name, booklet, chunk), model)
        for fid, v in (obj.get("fields") or {}).items():
            if isinstance(v, dict):
                v["_has_instructions"] = bool(
                    ((proposals["fields"].get(fid) or {})
                     .get("instructions") or "").strip())
                verdicts[fid] = v
    return verdicts


def _rectify_prompt(form_name: str, booklet: str, failures: List[dict]) -> str:
    spec = ('{"fields": {"<field_id>": {"instructions": "...", '
            '"details": "...", "format_hint": "..."}}}')
    return (guidance_contract.CONTRACT_TEXT
            + "\n\nFORM: " + form_name
            + "\n\nOFFICIAL INSTRUCTIONS TEXT:\n---\n" + booklet + "\n---\n"
            + "\nREVISE the guidance for these fields. Each carries the "
              "judge's objections -- fix EXACTLY those (drop unsupported "
              "claims, remove advice phrasing, restore omitted qualifying "
              "clauses in details, or emit an empty string when the sources "
              "support nothing):\n"
            + json.dumps(failures, ensure_ascii=False, indent=1)
            + "\n\nOUTPUT -- one JSON object, nothing else:\n" + spec)


def verify_and_rectify(schema: dict, proposals: dict, booklet: str,
                       form_name: str, author_model: str,
                       judge_model: str = JUDGE_MODEL) -> List[dict]:
    """The bounded verify loop. MUTATES proposals in place per the KEEP rule;
    returns LintFinding-shaped flag dicts for the provenance block."""
    flags: List[dict] = []
    booklet_norm = guidance_contract.normalize_for_containment(booklet)
    fields_by_id = {f.get("id"): f for f in schema.get("fields", [])
                    if isinstance(f, dict)}
    try:
        verdicts = judge_proposals(schema, proposals, booklet, form_name,
                                   judge_model)
    except Exception as exc:  # noqa: BLE001  -- fail SAFE, not open
        for fid, e in list((proposals.get("fields") or {}).items()):
            if (e.get("instructions") or e.get("details")):
                proposals["fields"][fid] = {}
        proposals["form_details"] = ""
        flags.append({
            "severity": "WARNING", "rule": "instructions-enrich-unavailable",
            "path": "$.fields",
            "message": "guidance judge unavailable ("
                       + type(exc).__name__
                       + "); NO authored guidance was written -- "
                       "deterministic baseline kept for every field "
                       "(KEEP rule)"})
        return flags

    rectified: set = set()
    for _round in range(1, RECTIFY_MAX_ROUNDS + 1):
        failures = []
        for fid, v in verdicts.items():
            if not _passes(v):
                entry = proposals["fields"].get(fid) or {}
                failures.append({
                    "digest": field_digest(
                        fields_by_id.get(fid) or {"id": fid}),
                    "instructions": entry.get("instructions", ""),
                    "details": entry.get("details", ""),
                    "judge_objections": {
                        k: v.get(k) for k in
                        ("unsupported_claims", "omission_concerns",
                         "advice", "grounded", "useful_beyond_label")}})
        if not failures:
            break
        runner = llm_providers.resolve_json_runner(author_model)
        obj, _tok = runner(_rectify_prompt(form_name, booklet, failures),
                           author_model)
        for fid, e in (obj.get("fields") or {}).items():
            if not isinstance(e, dict) or fid not in proposals["fields"]:
                continue
            det = e.get("details")
            if isinstance(det, str) and det.strip():
                det, _dropped = repair_details_contiguity(det, booklet_norm)
                e["details"] = det
            proposals["fields"][fid] = {
                k: (e.get(k) or "").strip()
                for k in ("instructions", "details", "format_hint")}
            rectified.add(fid)
        verdicts = judge_proposals(schema, proposals, booklet, form_name,
                                   judge_model)

    # Completeness sweep FIRST: a field the judge silently OMITTED from its
    # JSON response has no verdict, and without this it would fall through to
    # write_kit as "llm-verified" with zero flags -- a fail-open hole in the
    # KEEP rule (wsao.5 fresh-eyes finding 1). Judge-omission is treated
    # identically to a safety fail: drop + flag.
    for fid, e in list((proposals.get("fields") or {}).items()):
        has_guidance = isinstance(e, dict) and (
            (e.get("instructions") or "").strip()
            or (e.get("details") or "").strip()
            or (e.get("format_hint") or "").strip())
        if has_guidance and fid not in verdicts:
            proposals["fields"][fid] = {}
            flags.append({
                "severity": "WARNING",
                "rule": "instructions-ungrounded-dropped",
                "path": "fields (id=" + fid + ").help",
                "message": "the judge omitted this field from its response "
                           "-- treated as UNVERIFIED: proposed text DROPPED, "
                           "deterministic baseline kept (KEEP rule)"})

    for fid, v in verdicts.items():
        safety_fail = (not v.get("grounded")) or v.get("advice") \
            or v.get("omission_concerns")
        if not safety_fail:
            if fid in rectified:
                flags.append({
                    "severity": "WARNING", "rule": "instructions-rectified",
                    "path": "fields (id=" + fid + ").help",
                    "message": "guidance was revised by the verify loop and "
                               "passed on re-judge -- review the revision"})
            if (v.get("_has_instructions")
                    and not v.get("useful_beyond_label")
                    and fid not in rectified):
                # rectified fields already carry a review flag above --
                # a second flag for the same id would double-list it on
                # the editor worklist (round-2 cosmetic finding)
                # usefulness is a QUALITY signal, not a SAFETY property --
                # grounded-but-thin text is harmless, so it FLAGS for the
                # human worklist, never drops (wsao.5 measured: the drop
                # policy destroyed 22 genuine-guidance fields on judge
                # false-negatives)
                flags.append({
                    "severity": "WARNING",
                    "rule": "instructions-rectified",
                    "path": "fields (id=" + fid + ").help",
                    "message": "judge scored these instructions as adding "
                               "little beyond the label -- kept (grounded + "
                               "no advice), review for substance"})
        else:
            proposals["fields"][fid] = {}
            reasons = ((v.get("unsupported_claims") or [])[:2]
                       or (v.get("omission_concerns") or [])[:2]
                       or (["advice phrasing"] if v.get("advice")
                           else ["not grounded"]))
            flags.append({
                "severity": "WARNING",
                "rule": "instructions-ungrounded-dropped",
                "path": "fields (id=" + fid + ").help",
                "message": "authored guidance FAILED A SAFETY CHECK "
                           "(grounding/advice/omission) after "
                           + str(RECTIFY_MAX_ROUNDS)
                           + " rectify rounds -- proposed text DROPPED, "
                           "deterministic baseline kept (KEEP rule): "
                           + "; ".join(str(r) for r in reasons)})
    return flags


def tu_map_from_pdf(pdf_path: str) -> Dict[str, str]:
    """pdf_field_name -> /TU tooltip, straight from the form PDF widgets.
    Indexed by BOTH the full widget name and its LEAF segment (schemas store
    the leaf: 'P1_Line3a_FamilyName[0]' vs the PDF's
    'form1[0].#subform[0].P1_Line3a_FamilyName[0]')."""
    out: Dict[str, str] = {}
    doc = fitz.open(pdf_path)
    try:
        for page in doc:
            for w in page.widgets() or []:
                tu = getattr(w, "field_label", None)
                if w.field_name and tu:
                    out[w.field_name] = tu
                    leaf = w.field_name.rsplit(".", 1)[-1]
                    # a leaf name shared by two widgets with DIFFERENT /TU is
                    # ambiguous -- drop it rather than guess
                    if leaf in out and out[leaf] != tu:
                        out[leaf] = ""
                    else:
                        out[leaf] = tu
    finally:
        doc.close()
    return {k: v for k, v in out.items() if v}


def bootstrap_provenance(schema: dict, tu_map: Dict[str, str]) -> Dict[str, dict]:
    """Legacy kits carry no provenance, so 'no record => human-owned' would
    freeze them forever (the sprint-16 i-90 no-op trap). A field whose
    current instructions EXACTLY match its /TU tooltip is mechanically
    machine-owned (source: tu); anything else stays protected."""
    prov: Dict[str, dict] = {}
    for f in schema.get("fields", []):
        if not isinstance(f, dict):
            continue
        help_obj = f.get("help") if isinstance(f.get("help"), dict) else {}
        instr = help_obj.get("instructions")
        if not (isinstance(instr, str) and instr.strip()):
            continue
        pfn = f.get("pdf_field_name") or next(
            (o.get("pdf_field_name") for o in (f.get("options") or [])
             if isinstance(o, dict) and o.get("pdf_field_name")), None)
        tu = tu_map.get(pfn) if pfn else None
        if tu is not None and instr.strip() == tu.strip():
            prov[f["id"]] = {"source": "tu",
                             "instructions_sha1": _sha1(instr)}
    return prov


def write_kit(kit_dir: str, proposals: dict, booklet: str, flags: List[dict],
              model: str, judge_model: str) -> dict:
    """Provenance-guarded write to the CANONICAL kit schema.json. Machine-
    owned or blank fields update; human-owned fields are skipped (their
    protection IS the feature). Returns a summary."""
    schema_path = os.path.join(kit_dir, "schema.json")
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)

    bakeoff = schema.setdefault("_bakeoff", {}).setdefault("authoring", {})
    prior = bakeoff.get("instructions_enrich") or {}
    prov: Dict[str, dict] = dict(prior.get("provenance") or {})

    pdf_path = os.path.join(kit_dir, "form.pdf")
    if os.path.exists(pdf_path) and not prov:
        prov.update(bootstrap_provenance(schema, tu_map_from_pdf(pdf_path)))

    written = skipped_human = 0
    for f in schema.get("fields", []):
        if not isinstance(f, dict):
            continue
        entry = (proposals.get("fields") or {}).get(f.get("id"))
        if not isinstance(entry, dict):
            continue
        help_obj = f.get("help") if isinstance(f.get("help"), dict) else {}
        rec = prov.get(f.get("id")) or {}
        cur = help_obj.get("instructions")
        cur = cur if isinstance(cur, str) else ""
        machine_owned = (not cur.strip()) or bool(
            rec and _sha1(cur) == rec.get("instructions_sha1"))
        if not machine_owned:
            skipped_human += 1
            continue
        changed = False
        for key in ("instructions", "details", "format_hint"):
            val = (entry.get(key) or "").strip()
            if val:
                help_obj[key] = val
                changed = True
        if changed:
            f["help"] = help_obj
            prov[f["id"]] = {
                "source": "llm-verified",
                "instructions_sha1": _sha1(help_obj.get("instructions", "")),
                "details_sha1": _sha1(help_obj.get("details", "")),
                "format_hint_sha1": _sha1(help_obj.get("format_hint", "")),
            }
            written += 1
    meta = schema.setdefault("form_metadata", {})
    fd = (proposals.get("form_details") or "").strip()
    if fd:
        meta["details"] = fd
    meta["booklet_text"] = booklet

    bakeoff["instructions_enrich"] = {
        "model": model, "judge_model": judge_model,
        "booklet_sha1": _sha1(booklet),
        "provenance": prov, "flags": flags,
    }
    with open(schema_path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2, ensure_ascii=False)
    return {"written": written, "skipped_human": skipped_human,
            "flags": len(flags)}

if __name__ == "__main__":
    sys.exit(main())
