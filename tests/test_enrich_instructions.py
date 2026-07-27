"""Unit tests for the guidance-enrichment engine's offline mechanics
(bd polyglot-pdf-wsao.4). No live model calls -- the runner is exercised by
the recorded w7 dry-run; these pin the digest/prompt/apply/report plumbing.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "enrich_instructions", REPO / "scripts" / "authoring" /
    "enrich_instructions.py")
ei = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ei)

from backend.services import guidance_contract as gc  # noqa: E402


SCHEMA = {
    "form_metadata": {"title": "Form W-7", "version": "1"},
    "fields": [
        {"id": "reason_a", "name": "a. Tax treaty benefit", "type": "checkbox",
         "help": {"instructions": "TU tooltip text."}},
        {"id": "name1", "name": "Legal name", "type": "text",
         "options": []},
        {"id": "sig", "name": "Signature", "type": "signature"},
        {"id": "locked", "name": "Locked", "type": "text", "read_only": True},
    ],
    "sections": [], "parts": [],
}


def test_askable_excludes_signature_and_readonly():
    ids = [f["id"] for f in ei.askable_fields(SCHEMA)]
    assert ids == ["reason_a", "name1"]


def test_field_digest_carries_contract_signals():
    d = ei.field_digest(SCHEMA["fields"][0])
    assert d["id"] == "reason_a" and d["type"] == "checkbox"
    assert d["existing_instructions"] == "TU tooltip text."
    assert "options" not in d  # empty options list omitted
    d2 = ei.field_digest({"id": "x", "name": "X", "type": "radio",
                          "options": [{"value": "v", "label": "L",
                                       "pdf_field_name": "leak[0]"}],
                          "show_if": {"field": "y", "operator": "is_checked"}})
    # options sanitized to value/label; show_if passes through so the model
    # never restates modeled conditions
    assert d2["options"] == [{"value": "v", "label": "L"}]
    assert d2["show_if"]["field"] == "y"


def test_build_prompt_carries_contract_booklet_and_spec():
    p = ei.build_prompt("Form W-7", "BOOKLET TEXT HERE",
                        [ei.field_digest(SCHEMA["fields"][0])])
    assert gc.CONTRACT_TEXT in p
    assert "BOOKLET TEXT HERE" in p
    assert "form_details" in p and "containment check" in p


def test_apply_to_copy_never_mutates_and_sets_floor():
    proposals = {"fields": {"reason_a": {
        "instructions": "Check the one box that applies.",
        "details": "## a. Tax treaty benefit\nVerbatim text.",
        "format_hint": "one box"}},
        "form_details": "Who Is Eligible: verbatim."}
    applied = ei.apply_to_copy(SCHEMA, proposals, "FULL BOOKLET")
    # original untouched
    assert SCHEMA["fields"][0]["help"] == {"instructions": "TU tooltip text."}
    fa = [f for f in applied["fields"] if f["id"] == "reason_a"][0]
    assert fa["help"]["instructions"] == "Check the one box that applies."
    assert fa["help"]["details"].startswith("## a.")
    assert fa["help"]["format_hint"] == "one box"
    assert applied["form_metadata"]["details"] == "Who Is Eligible: verbatim."
    assert applied["form_metadata"]["booklet_text"] == "FULL BOOKLET"
    # empty-string proposal keys never clobber
    applied2 = ei.apply_to_copy(SCHEMA, {"fields": {"reason_a": {
        "instructions": "  "}}, "form_details": ""}, "B")
    fa2 = [f for f in applied2["fields"] if f["id"] == "reason_a"][0]
    assert fa2["help"]["instructions"] == "TU tooltip text."


def test_find_booklet_glob_fallback(tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "w7-instructions.pdf").write_bytes(b"%PDF")
    assert ei.find_booklet(str(kit), None).endswith("w7-instructions.pdf")
    assert ei.find_booklet(str(kit), "explicit.pdf") == "explicit.pdf"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert ei.find_booklet(str(empty), None) is None


def test_repair_details_contiguity_splits_glue_and_drops_paraphrase():
    """The deterministic contiguity repairer (wsao.4 outer review): a glued
    paragraph of two non-adjacent verbatim passages is SPLIT at the contained
    -prefix boundary (pure re-formatting); genuine paraphrase is DROPPED and
    reported, never kept."""
    from backend.services import guidance_contract as gc
    booklet = ("First verbatim sentence about the ITIN. Skipped middle "
               "sentence that the model omitted. Second verbatim sentence "
               "about documentation.")
    bn = gc.normalize_for_containment(booklet)
    glued = ("First verbatim sentence about the ITIN. Second verbatim "
             "sentence about documentation.")
    repaired, dropped = ei.repair_details_contiguity(glued, bn)
    assert dropped == []
    paras = [p for p in repaired.split("\n\n") if p.strip()]
    assert len(paras) == 2
    assert all(gc.check_containment_normalized(p, bn).contained
               for p in paras)
    # paraphrase drops
    repaired2, dropped2 = ei.repair_details_contiguity(
        "A wholly invented summary sentence.", bn)
    assert repaired2 == "" and len(dropped2) == 1
    # already-contiguous text passes through untouched
    ok = "First verbatim sentence about the ITIN."
    repaired3, dropped3 = ei.repair_details_contiguity(ok, bn)
    assert repaired3 == ok and dropped3 == []


def test_repairer_whitespace_blank_lines_and_interleaved_paraphrase():
    """wsao.4 outer re-review round: (a) a whitespace-bearing blank line
    ('\n \n') must NOT silently lose the following verbatim segment; (b) an
    interleaved [verbatim][paraphrase][verbatim] span keeps BOTH verbatim
    pieces and drops only the paraphrase sentence (bd polyglot-pdf-9v3p)."""
    from backend.services import guidance_contract as gc
    booklet = ("Alpha verbatim sentence about the ITIN process. "
               "Beta verbatim sentence about required documentation.")
    bn = gc.normalize_for_containment(booklet)
    # (a) whitespace blank-line separator
    repaired, dropped = ei.repair_details_contiguity(
        "Alpha verbatim sentence about the ITIN process.\n \n"
        "Beta verbatim sentence about required documentation.", bn)
    assert "Alpha verbatim" in repaired and "Beta verbatim" in repaired
    assert dropped == []
    # (b) interleaved paraphrase keeps A and C, drops only B
    repaired2, dropped2 = ei.repair_details_contiguity(
        "Alpha verbatim sentence about the ITIN process. "
        "A wholly invented middle claim goes here. "
        "Beta verbatim sentence about required documentation.", bn)
    assert "Alpha verbatim" in repaired2 and "Beta verbatim" in repaired2
    assert len(dropped2) == 1 and "invented middle" in dropped2[0]
