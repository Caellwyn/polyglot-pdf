"""Guidance content contract + lint rules (bd polyglot-pdf-wsao.3).

Pins: the containment normalization spec (the zero-trust core of the details
channel), the anti-restatement heuristic, and every new schema_lint guidance
rule -- one synthetic violation fixture per rule, plus the exit-criterion
check that the coverage rule fires on the REAL w7 kit (0/59 authored
guidance today).

ASCII only (CLAUDE.md scar #6). Unicode punctuation in fixtures is
chr()-composed.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services import guidance_contract as gc
from backend.services.schema_lint import lint_schema

REPO = Path(__file__).resolve().parents[3]

CURLY_APOS = chr(0x2019)
EM_DASH = chr(0x2014)
NBSP = chr(0x00A0)


# --- containment normalization -----------------------------------------------

def test_containment_exact_verbatim_passes():
    src = "If you check this box, you must also check box h."
    res = gc.check_containment("you must also check box h", src)
    assert res.contained and res.matched_at >= 0
    assert "check box h" in res.matched_span


def test_containment_survives_curly_quotes_hyphenation_and_whitespace():
    # The booklet PDF renders curly apostrophes, line-break hyphenation, and
    # hard line wraps; the excerpt is typed clean. Both normalize to the same
    # string -- the PINNED spec.
    src = ("Certain nonresident aliens must get an ITIN to claim tax" + NBSP +
           "treaty benefits even if they don" + CURLY_APOS + "t have to file "
           "a U.S. federal tax return with third-party with-\nholding " +
           EM_DASH + " see Pub. 901.")
    excerpt = ("certain nonresident aliens must get an ITIN to claim tax "
               "treaty benefits even if they don't have to file a U.S. "
               "federal tax return with third-party withholding - see Pub. 901.")
    assert gc.check_containment(excerpt, src).contained


def test_containment_rejects_paraphrase():
    src = "You must attach the documentation required under the exception."
    res = gc.check_containment(
        "Attach whatever documents the exception needs.", src)
    assert not res.contained and res.matched_at == -1


def test_details_paragraphs_excludes_heading_scaffolding():
    details = ("## a. Tax treaty benefit\n"
               "Certain nonresident aliens must get an ITIN.\n\n"
               "Exception 1.\n"
               "This exception may apply for passive income.")
    paras = gc.details_paragraphs(details)
    assert paras == ["Certain nonresident aliens must get an ITIN.",
                     "This exception may apply for passive income."]


def test_label_restatement_detects_filler_and_passes_real_guidance():
    assert gc.is_label_restatement(
        "Select your eye color.", "Eye Color",
        ["Brown", "Blue", "Green"])
    assert not gc.is_label_restatement(
        "This code appears on the front of your Permanent Resident Card.",
        "Class of Admission", [])


# --- lint rules: one synthetic violation per rule ----------------------------

def _schema(fields, booklet=None):
    meta = {"title": "T", "version": "1"}
    if booklet is not None:
        meta["booklet_text"] = booklet
    return {"metadata_unused": {}, "form_metadata": meta, "fields": fields,
            "sections": [], "parts": []}


def _rules(findings):
    return [f.rule for f in findings]


def test_lint_missing_instructions_aggregates_and_respects_exclusions():
    findings = lint_schema(_schema([
        {"id": "a", "name": "A", "type": "text"},
        {"id": "b", "name": "B", "type": "text", "read_only": True},
        {"id": "c", "name": "C", "type": "signature"},
        {"id": "d", "name": "D", "type": "text",
         "help": {"instructions": "Enter the code from your card."}},
    ]))
    hits = [f for f in findings if f.rule == "help-instructions-missing"]
    # ONE aggregated finding (never per-field -- flood guard), counting only
    # the askable/uncovered field 'a' (b read_only + c signature excluded, d
    # covered).
    assert len(hits) == 1
    assert "1 of 2 askable" in hits[0].message and "a" in hits[0].message


def test_lint_too_long_restatement_and_screen_ref():
    findings = lint_schema(_schema([
        {"id": "long", "name": "L", "type": "text",
         "help": {"instructions": "x" * (gc.INSTRUCTIONS_HARD_CHARS + 1)}},
        {"id": "restate", "name": "Eye Color", "type": "select",
         "options": [{"value": "brown", "label": "Brown"}],
         "help": {"instructions": "Select your eye color."}},
        {"id": "deixis", "name": "D", "type": "text",
         "help": {"instructions": "See page 7 of the instructions above."}},
    ]))
    rules = _rules(findings)
    assert "help-instructions-too-long" in rules
    assert "help-instructions-label-restatement" in rules
    assert "help-instructions-screen-ref" in rules


def test_lint_containment_failure_and_floor_missing():
    booklet = "Certain nonresident aliens must get an ITIN to claim benefits."
    # Paragraph NOT in the booklet -> not-contained finding with the paragraph
    # head quoted in the message.
    findings = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": "This sentence was invented by a model."}},
    ], booklet=booklet))
    hits = [f for f in findings if f.rule == "help-details-not-contained"]
    assert len(hits) == 1
    assert "This sentence was invented" in hits[0].message

    # Same details but NO booklet floor -> the no-reference-floor finding
    # instead (containment cannot run).
    findings2 = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": "Anything at all."}},
    ]))
    assert "help-details-no-reference-floor" in _rules(findings2)
    assert "help-details-not-contained" not in _rules(findings2)


def test_lint_containment_passes_verbatim_excerpt():
    booklet = ("a. Tax treaty benefit. Certain nonresident aliens must get "
               "an ITIN to claim tax treaty benefits even if they don" +
               CURLY_APOS + "t have to file a return.")
    findings = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": "## a. Tax treaty benefit\n"
                             "Certain nonresident aliens must get an ITIN to "
                             "claim tax treaty benefits even if they don't "
                             "have to file a return."}},
    ], booklet=booklet))
    assert "help-details-not-contained" not in _rules(findings)


def test_lint_oversize_and_headings_missing():
    booklet_words = ("word " * (gc.DETAILS_OVERSIZE_WORDS + 10)).strip()
    findings = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": booklet_words}},
    ], booklet=booklet_words))
    rules = _rules(findings)
    assert "help-details-oversize" in rules
    assert "help-details-headings-missing" in rules  # long + zero headings


def test_guidance_rules_are_warning_severity_only():
    findings = lint_schema(_schema([
        {"id": "a", "name": "A", "type": "text"},
    ]))
    for f in findings:
        if f.rule.startswith("help-"):
            assert f.severity == "WARNING"


# --- exit criterion: fires on the real w7 kit --------------------------------

def test_w7_kit_coverage_gap_is_flagged():
    """The shipped w7 kit has 0/59 authored guidance (sprint-16 recon) -- the
    coverage rule must surface that worklist. If a future backfill (wsao.7)
    authors guidance, this asserts the remaining gap count matches reality
    rather than a frozen number."""
    kit = REPO / "form-kits" / "w7" / "schema.json"
    schema = json.loads(kit.read_text(encoding="utf-8"))
    findings = lint_schema(schema)
    missing = [f for f in findings if f.rule == "help-instructions-missing"]
    assert len(missing) == 1  # ONE aggregated worklist finding
    uncovered = [f for f in schema["fields"]
                 if not f.get("read_only") and f.get("type") != "signature"
                 and not ((f.get("help") or {}).get("instructions") or "").strip()]
    assert len(uncovered) > 0  # w7 has a real coverage gap today
    assert f"{len(uncovered)} of" in missing[0].message
