"""Toggle hand-crafted help.details onto the LOCAL w7 kit for the wsao.2
measurement gate (sprint-16 plan, staging step 2).

Injects the W-7 booklet's "Reason You're Submitting Form W-7" section
(pp. 6-8, categories a-h + Exceptions 1-5) VERBATIM into
frontend/public/form-kits/w7/schema.json:

  - reason_a.help.details  = the whole reason section (the worst-case inline
    block the A/B measures, ~3.4k tokens)
  - reason_a.help.instructions = a short hand-written overview (the two-channel
    shape the plan specifies)
  - form_metadata.booklet_text = the FULL booklet text (secretary floor)

The extraction is PROGRAMMATIC from form-kits/w7/w7-instructions.pdf, so the
details channel is verbatim by construction (the sprint-16 extractive
contract). --revert restores the schema from git. The SHIPPED kit is never
committed with these edits -- this script exists so the measurement can toggle
arms; the real bake is the enrichment engine's job (wsao.4+).

Usage (from the worktree root, backend venv python):
    python tests/e2e/voice-harness/apply_details_w7.py --apply
    python tests/e2e/voice-harness/apply_details_w7.py --revert

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

WT = Path(__file__).resolve().parents[3]
SCHEMA = WT / "frontend" / "public" / "form-kits" / "w7" / "schema.json"
BOOKLET = WT / "form-kits" / "w7" / "w7-instructions.pdf"

SECTION_START = "Reason You"  # "Reason You're Submitting Form W-7" (curly quote)
SECTION_END = "Line Instructions"

# Short overview channel -- hand-written per the sprint-16 two-channel shape.
INSTRUCTIONS = (
    "Check the one box that best explains why you're submitting Form W-7 -- "
    "required even for renewals; if more than one applies, pick the best fit. "
    "Note: boxes a and f (treaty benefits) also require checking box h with an "
    "exception number, and several categories require extra information on "
    "other lines."
)

FOOTER_RE = re.compile(
    r"^(Instructions for Form W-7 \(Rev\. December 2024\)|\d{1,2})\s*$")


def _clean(text: str) -> str:
    """Drop page-footer lines and the CAUTION glyph artifacts; keep everything
    else verbatim (line breaks included -- the containment lint normalizes)."""
    out = []
    for line in text.splitlines():
        if FOOTER_RE.match(line.strip()):
            continue
        if line.strip() in ("CAUTION", "!", "TIP"):
            continue
        out.append(line)
    return "\n".join(out).strip()


def extract_reason_section() -> str:
    doc = fitz.open(BOOKLET)
    full = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    # The heading appears in the table of contents too -- anchor the search
    # after the BODY "Specific Instructions" heading (which follows the TOC).
    body = full.find("Specific Instructions", full.find("Specific Instructions") + 1)
    if body < 0:
        body = 0
    start = full.find(SECTION_START, body)
    end = full.find(SECTION_END, start)
    if start < 0 or end < 0:
        raise SystemExit("could not locate the reason section in the booklet")
    section = _clean(full[start:end])
    if "Exception 5" not in section or len(section) < 5000:
        raise SystemExit("reason-section extraction looks wrong (%d chars)"
                         % len(section))
    return section


def extract_full_booklet() -> str:
    doc = fitz.open(BOOKLET)
    full = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    doc.close()
    return _clean(full)


BACKUP = SCHEMA.with_suffix(".json.vff-backup")


def apply() -> None:
    # frontend/public/form-kits/ is GITIGNORED (synced from form-kits/), so
    # revert restores from a sidecar backup, not git.
    if not BACKUP.exists():
        BACKUP.write_bytes(SCHEMA.read_bytes())
    schema = json.loads(BACKUP.read_text(encoding="utf-8"))
    details = extract_reason_section()
    for field in schema["fields"]:
        if field["id"] == "reason_a":
            help_obj = field.get("help") or {}
            help_obj["instructions"] = INSTRUCTIONS
            help_obj["details"] = details
            field["help"] = help_obj
            break
    else:
        raise SystemExit("reason_a not found in w7 schema")
    schema.setdefault("form_metadata", {})["booklet_text"] = extract_full_booklet()
    SCHEMA.write_text(json.dumps(schema, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    print("applied: reason_a.help.details=%d chars (~%d tokens), "
          "booklet_text=%d chars" % (
              len(details), len(details) // 4,
              len(schema["form_metadata"]["booklet_text"])))


def revert() -> None:
    if not BACKUP.exists():
        raise SystemExit("no backup to revert from (never applied?)")
    SCHEMA.write_bytes(BACKUP.read_bytes())
    BACKUP.unlink()
    print("reverted from backup:", SCHEMA.relative_to(WT).as_posix())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true")
    group.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    (apply if args.apply else revert)()
