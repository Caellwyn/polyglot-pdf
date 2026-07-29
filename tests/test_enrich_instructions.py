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


def test_write_kit_no_clobber_and_provenance(tmp_path):
    """wsao.5 exit criterion 2 (first half): a human-owned field survives a
    re-run untouched; blank/machine-owned fields update with provenance."""
    import json as _json
    kit = tmp_path / "kit"
    kit.mkdir()
    schema = {
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [
            {"id": "blank", "name": "B", "type": "text"},
            {"id": "human", "name": "H", "type": "text",
             "help": {"instructions": "Hand-authored by the maintainer."}},
        ],
        "sections": [], "parts": [],
    }
    (kit / "schema.json").write_text(_json.dumps(schema), encoding="utf-8")
    proposals = {"fields": {
        "blank": {"instructions": "Authored A.", "details": "", "format_hint": ""},
        "human": {"instructions": "Machine overwrite attempt.",
                  "details": "", "format_hint": ""}},
        "form_details": ""}
    s1 = ei.write_kit(str(kit), proposals, "BOOKLET", [], "m", "j")
    assert s1["written"] == 1 and s1["skipped_human"] == 1
    saved = _json.loads((kit / "schema.json").read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in saved["fields"]}
    assert by_id["blank"]["help"]["instructions"] == "Authored A."
    assert by_id["human"]["help"]["instructions"] == \
        "Hand-authored by the maintainer."
    prov = saved["_bakeoff"]["authoring"]["instructions_enrich"]["provenance"]
    assert prov["blank"]["source"] == "llm-verified"
    # THE WRITER IS THE FEATURE (bd anim, closeout Opus round): the staleness
    # lint rule is deliberately silent when identity_sha1 is absent, so if the
    # bake ever stops writing it the whole gate turns off with no failing test
    # and no runtime signal. This assertion is the only thing standing between
    # a dropped write and a silently disabled feature.
    assert prov["blank"]["identity_sha1"] == gc.identity_sha1(by_id["blank"])
    # machine-owned field UPDATES on re-run (hash matches recorded)
    proposals2 = {"fields": {"blank": {"instructions": "Authored A v2.",
                                       "details": "", "format_hint": ""}},
                  "form_details": ""}
    s2 = ei.write_kit(str(kit), proposals2, "BOOKLET", [], "m", "j")
    saved2 = _json.loads((kit / "schema.json").read_text(encoding="utf-8"))
    assert s2["written"] == 1
    assert {f["id"]: f for f in saved2["fields"]}["blank"]["help"][
        "instructions"] == "Authored A v2."
    # then a HUMAN EDIT to that same field protects it from round 3
    saved2["fields"][0]["help"]["instructions"] = "Maintainer fixed this."
    (kit / "schema.json").write_text(_json.dumps(saved2), encoding="utf-8")
    s3 = ei.write_kit(str(kit), proposals2, "BOOKLET", [], "m", "j")
    assert s3["written"] == 0 and s3["skipped_human"] >= 1
    saved3 = _json.loads((kit / "schema.json").read_text(encoding="utf-8"))
    assert {f["id"]: f for f in saved3["fields"]}["blank"]["help"][
        "instructions"] == "Maintainer fixed this."


def test_verify_unavailable_keeps_baseline(monkeypatch):
    """wsao.5 exit criterion 2 (second half): judge unavailable => NO
    authored text survives (KEEP rule) + the unavailable flag."""
    def _boom(model):
        def runner(prompt, m):
            raise RuntimeError("no credentials")
        return runner
    monkeypatch.setattr(ei.llm_providers, "resolve_json_runner", _boom)
    proposals = {"fields": {"a": {"instructions": "X", "details": "Y"}},
                 "form_details": "Z"}
    flags = ei.verify_and_rectify(
        {"fields": [{"id": "a", "name": "A", "type": "text"}]},
        proposals, "BOOKLET", "T", "author-model")
    assert proposals["fields"]["a"] == {}
    assert proposals["form_details"] == ""
    assert [f["rule"] for f in flags] == ["instructions-enrich-unavailable"]


def test_bootstrap_provenance_marks_tu_identical_only():
    """wsao.5 exit criterion 3 shape: exact /TU match => machine-owned;
    anything else stays protected."""
    schema = {"fields": [
        {"id": "tu_match", "pdf_field_name": "A[0]",
         "help": {"instructions": "Enter Family Name (Last Name)."}},
        {"id": "edited", "pdf_field_name": "B[0]",
         "help": {"instructions": "A human improved this text."}},
        {"id": "no_help", "pdf_field_name": "C[0]"},
    ]}
    prov = ei.bootstrap_provenance(schema, {
        "A[0]": "Enter Family Name (Last Name).",
        "B[0]": "Original tooltip that was edited away.",
        "C[0]": "Anything."})
    assert set(prov) == {"tu_match"}
    assert prov["tu_match"]["source"] == "tu"
    # /TU-bootstrapped fields are covered by the staleness gate too -- the
    # record must carry the field's identity hash (bd anim, closeout Opus
    # round: the writer had zero coverage).
    assert prov["tu_match"]["identity_sha1"] == \
        gc.identity_sha1(schema["fields"][0])


def test_lint_reemits_guidance_flags():
    from backend.services.schema_lint import lint_schema
    schema = {
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [], "sections": [], "parts": [],
        "_bakeoff": {"authoring": {"instructions_enrich": {"flags": [
            {"severity": "ERROR",  # pinned back to WARNING on re-emit
             "rule": "instructions-ungrounded-dropped",
             "path": "fields (id=x).help", "message": "dropped"},
            {"rule": "not-a-guidance-rule", "path": "p", "message": "m"},
            "junk",
        ]}}},
    }
    findings = lint_schema(schema)
    hits = [f for f in findings
            if f.rule == "instructions-ungrounded-dropped"]
    assert len(hits) == 1 and hits[0].severity == "WARNING"
    assert not [f for f in findings if f.rule == "not-a-guidance-rule"]


def test_judge_omission_drops_field(monkeypatch):
    """A field the judge SILENTLY OMITS from its response must be treated as
    unverified -- dropped + flagged, never written as llm-verified (wsao.5
    fresh-eyes finding 1: the fail-open hole in the KEEP rule)."""
    def _partial(model):
        def runner(prompt, m):
            # verdict for field a only; field b silently omitted
            return ({"fields": {"a": {
                "grounded": True, "unsupported_claims": [],
                "useful_beyond_label": True, "omission_concerns": [],
                "advice": False}}}, 100)
        return runner
    monkeypatch.setattr(ei.llm_providers, "resolve_json_runner", _partial)
    proposals = {"fields": {
        "a": {"instructions": "Fine.", "details": "", "format_hint": ""},
        "b": {"instructions": "INVENTED legal claim never verified.",
              "details": "", "format_hint": ""}},
        "form_details": ""}
    schema = {"fields": [{"id": "a", "name": "A", "type": "text"},
                         {"id": "b", "name": "B", "type": "text"}]}
    flags = ei.verify_and_rectify(schema, proposals, "BOOKLET", "T", "m")
    assert proposals["fields"]["a"]["instructions"] == "Fine."
    assert proposals["fields"]["b"] == {}
    omission = [f for f in flags
                if f["rule"] == "instructions-ungrounded-dropped"
                and "id=b" in f["path"]]
    assert len(omission) == 1 and "omitted" in omission[0]["message"]


def test_format_hint_only_field_is_judged_and_swept(monkeypatch):
    """A format_hint-only field must reach the judge (write_kit stamps
    format_hint llm-verified) and, when the judge omits it, be dropped by
    the completeness sweep (wsao.5 fresh-eyes round 2)."""
    seen_prompts = []
    def _partial(model):
        def runner(prompt, m):
            seen_prompts.append(prompt)
            return ({"fields": {"a": {
                "grounded": True, "unsupported_claims": [],
                "useful_beyond_label": True, "omission_concerns": [],
                "advice": False}}}, 100)
        return runner
    monkeypatch.setattr(ei.llm_providers, "resolve_json_runner", _partial)
    proposals = {"fields": {
        "a": {"instructions": "Fine.", "details": "", "format_hint": ""},
        "fh_only": {"instructions": "", "details": "",
                    "format_hint": "MM/DD/YYYY"}},
        "form_details": ""}
    schema = {"fields": [{"id": "a", "name": "A", "type": "text"},
                         {"id": "fh_only", "name": "F", "type": "text"}]}
    flags = ei.verify_and_rectify(schema, proposals, "BOOKLET", "T", "m")
    # the format_hint-only field was SENT to the judge...
    assert any("fh_only" in p and "MM/DD/YYYY" in p for p in seen_prompts)
    # ...and, having been omitted from the verdicts, dropped + flagged
    assert proposals["fields"]["fh_only"] == {}
    assert any(f["rule"] == "instructions-ungrounded-dropped"
               and "id=fh_only" in f["path"] for f in flags)


def test_thin_verdict_on_rectified_field_flags_once(monkeypatch):
    """A field that was rectified AND judged thin gets ONE flag, not two
    (round-2 cosmetic finding: double-listing on the editor worklist)."""
    calls = {"n": 0}
    def _runner_factory(model):
        def runner(prompt, m):
            calls["n"] += 1
            if "REVISE the guidance" in prompt:
                return ({"fields": {"a": {
                    "instructions": "Revised.", "details": "",
                    "format_hint": ""}}}, 100)
            verdict = {"grounded": True, "unsupported_claims": [],
                       "omission_concerns": [], "advice": False,
                       # thin on every judge pass; unsupported on the first
                       "useful_beyond_label": False}
            if calls["n"] == 1:
                verdict = dict(verdict, grounded=False,
                               unsupported_claims=["bogus"])
            return ({"fields": {"a": verdict}}, 100)
        return runner
    monkeypatch.setattr(ei.llm_providers, "resolve_json_runner",
                        _runner_factory)
    proposals = {"fields": {"a": {"instructions": "Original.",
                                  "details": "", "format_hint": ""}},
                 "form_details": ""}
    schema = {"fields": [{"id": "a", "name": "A", "type": "text"}]}
    flags = ei.verify_and_rectify(schema, proposals, "BOOKLET", "T", "m")
    mine = [f for f in flags if "id=a" in f["path"]]
    assert len(mine) == 1 and mine[0]["rule"] == "instructions-rectified"


def test_write_kit_protects_details_only_human_edit(tmp_path):
    """The ownership gate covers EVERY channel (outer review finding): a
    human edit to details alone -- instructions still hash-matching -- must
    protect the field; and a hand-authored details with blank instructions
    and no record is human-owned from the start."""
    import json as _json
    kit = tmp_path / "kit"
    kit.mkdir()
    schema = {
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [
            {"id": "f1", "name": "A", "type": "text"},
            {"id": "hand_details", "name": "H", "type": "text",
             "help": {"details": "Curated verbatim excerpt."}},
        ],
        "sections": [], "parts": [],
    }
    (kit / "schema.json").write_text(_json.dumps(schema), encoding="utf-8")
    proposals = {"fields": {
        "f1": {"instructions": "I1.", "details": "D1.", "format_hint": ""},
        "hand_details": {"instructions": "X.", "details": "Machine D.",
                         "format_hint": ""}},
        "form_details": ""}
    s1 = ei.write_kit(str(kit), proposals, "B", [], "m", "j")
    saved = _json.loads((kit / "schema.json").read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in saved["fields"]}
    # blank-instructions + hand-authored details, no record => protected
    assert s1["skipped_human"] == 1
    assert by_id["hand_details"]["help"]["details"] == \
        "Curated verbatim excerpt."
    # now hand-edit ONLY details on the machine-written field
    by_id["f1"]["help"]["details"] = "Human curated this excerpt."
    (kit / "schema.json").write_text(_json.dumps(saved), encoding="utf-8")
    proposals2 = {"fields": {"f1": {"instructions": "I2.", "details": "D2.",
                                    "format_hint": ""}}, "form_details": ""}
    s2 = ei.write_kit(str(kit), proposals2, "B", [], "m", "j")
    saved2 = _json.loads((kit / "schema.json").read_text(encoding="utf-8"))
    f1 = {f["id"]: f for f in saved2["fields"]}["f1"]
    assert s2["written"] == 0 and s2["skipped_human"] >= 1
    assert f1["help"]["details"] == "Human curated this excerpt."
    assert f1["help"]["instructions"] == "I1."


def test_rectify_to_empty_flags_as_dropped(monkeypatch):
    """A field the rectifier EMPTIES (sources support nothing) is the same
    outcome as a KEEP-rule drop and must carry the same flag -- found by
    the wsao.5 re-bake, where 6 drops became 0 flags via this path."""
    calls = {"n": 0}
    def _runner_factory(model):
        def runner(prompt, m):
            if "REVISE the guidance" in prompt:
                return ({"fields": {"bad": {"instructions": "",
                                            "details": "",
                                            "format_hint": ""}}}, 100)
            calls["n"] += 1
            ok = {"grounded": True, "unsupported_claims": [],
                  "useful_beyond_label": True, "omission_concerns": [],
                  "advice": False}
            fields = {"good": dict(ok)}
            if calls["n"] == 1:
                fields["bad"] = dict(ok, grounded=False,
                                     unsupported_claims=["invented"])
            return ({"fields": fields}, 100)
        return runner
    monkeypatch.setattr(ei.llm_providers, "resolve_json_runner",
                        _runner_factory)
    proposals = {"fields": {
        "good": {"instructions": "Fine.", "details": "", "format_hint": ""},
        "bad": {"instructions": "Invented claim.", "details": "",
                "format_hint": ""}},
        "form_details": ""}
    schema = {"fields": [{"id": "good", "name": "G", "type": "text"},
                         {"id": "bad", "name": "B", "type": "text"}]}
    flags = ei.verify_and_rectify(schema, proposals, "BOOKLET", "T", "m")
    assert proposals["fields"]["bad"] == {}
    assert proposals["fields"]["good"]["instructions"] == "Fine."
    dropped = [f for f in flags
               if f["rule"] == "instructions-ungrounded-dropped"
               and "id=bad" in f["path"]]
    assert len(dropped) == 1 and "rectifier emptied" in dropped[0]["message"]
    assert not [f for f in flags if "id=good" in f["path"]]


def test_existing_provenance_locks_out_unrecorded_fields():
    """Once a kit carries ANY provenance, the tu bootstrap never runs again
    -- an unrecorded field with /TU-identical text stays human-protected
    (wsao.6 fresh-eyes round 2: the non-empty-but-non-covering case)."""
    schema = {
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [{"id": "tu_field", "pdf_field_name": "A[0]",
                    "name": "A", "type": "text",
                    "help": {"instructions": "Exact TU text."}}],
        "sections": [], "parts": [],
        "_bakeoff": {"authoring": {"instructions_enrich": {
            "provenance": {"some_other_field": {
                "source": "llm-verified", "instructions_sha1": "x"}}}}},
    }
    proposals = {"fields": {"tu_field": {
        "instructions": "Overwrite attempt.", "details": "",
        "format_hint": ""}}, "form_details": ""}
    s = ei.apply_proposals(schema, proposals, "B", [], "m", "j",
                           tu_map={"A[0]": "Exact TU text."})
    assert s["written"] == 0 and s["skipped_human"] == 1
    assert schema["fields"][0]["help"]["instructions"] == "Exact TU text."


def test_unmatched_proposal_ids_are_counted_not_applied(tmp_path):
    """bd anim exit criterion 3: a model-echoed id matching NO schema field is
    silently discarded by the apply loop (fail-safe) -- it must at least be
    COUNTED, or a systematic id-echo failure looks like 'the booklet said
    nothing'."""
    schema = {
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [{"id": "real", "name": "R", "type": "text"}],
        "sections": [], "parts": [],
    }
    proposals = {"fields": {
        "real": {"instructions": "Applied.", "details": "", "format_hint": ""},
        "hallucinated_id": {"instructions": "Never applied.",
                            "details": "", "format_hint": ""},
        "blank_one": {"instructions": "", "details": "", "format_hint": ""},
        # a model can return non-string junk under a hallucinated id; the
        # counter must SKIP it, not crash the whole apply (a bare .strip()
        # did, losing a metered run's output -- closeout Opus round 3)
        "junk_typed": {"instructions": {"nested": "obj"}, "details": 5,
                       "format_hint": None},
    }, "form_details": ""}
    summary = ei.apply_proposals(schema, proposals, "B", [], "m", "j")
    assert summary["written"] == 1
    # counted, and only the one carrying real STRING content
    assert summary["unmatched_proposal_ids"] == ["hallucinated_id"]
    # and genuinely NOT applied anywhere
    assert schema["fields"][0]["help"]["instructions"] == "Applied."
    assert len(schema["fields"]) == 1
