"""Tests for scripts/bakeoff/group_candidates.py (bd polyglot-pdf-h76m.12).

Exit criterion 1: the W-7 candidates contain the c1_2..c1_9 reason group
EXACTLY -- the widget family whose identity the live extraction failure
collapsed (the epic's trigger). Also pins the W-9 radio-kid family, the
suggest-don't-decide prompt block, and the flag gating in build_prompt.

Dumps are generated at test time from the committed kit PDFs (deterministic
PyMuPDF pass, no LLM). ASCII only.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))

import acroform_dump  # noqa: E402
import group_candidates as gc  # noqa: E402

_W7_PDF = _REPO / "form-kits" / "w7" / "form.pdf"
_W9_PDF = _REPO / "form-kits" / "w9-heldout" / "form.pdf"


def _dump_for(pdf_path: pathlib.Path, tmp_path: pathlib.Path) -> dict:
    out = tmp_path / (pdf_path.stem + "_dump.json")
    acroform_dump.main(["--json", str(out), str(pdf_path)])
    return json.loads(out.read_text(encoding="utf-8"))


def _by_leaves(candidates):
    return {tuple(c["leaves"]): c for c in candidates}


@pytest.mark.skipif(not _W7_PDF.exists(), reason="w7 kit not present")
def test_w7_candidates_contain_the_reason_group_exactly(tmp_path):
    """Exit criterion 1: c1_2[0]..c1_9[0] as ONE candidate -- no box missing,
    no neighbor absorbed (c1_1 is the application-type radio; c1_10 gender)."""
    candidates = gc.find_group_candidates(_dump_for(_W7_PDF, tmp_path))
    reason = tuple(f"c1_{i}[0]" for i in range(2, 10))
    groups = _by_leaves(candidates)
    assert reason in groups, sorted(groups)
    signals = "; ".join(groups[reason]["signals"])
    assert "numbered-leaf-run" in signals
    assert "shared-on-value" in signals


@pytest.mark.skipif(not _W7_PDF.exists(), reason="w7 kit not present")
def test_w7_radio_families_are_separate_candidates(tmp_path):
    candidates = gc.find_group_candidates(_dump_for(_W7_PDF, tmp_path))
    groups = _by_leaves(candidates)
    # The application-type pair and the 4-option id-doc radio each stand alone.
    assert ("c1_1[0]", "c1_1[1]") in groups
    assert tuple(f"c1_11[{i}]" for i in range(4)) in groups
    # No candidate mixes leaf families.
    for leaves in groups:
        bases = {l.split("[")[0].rstrip("0123456789") for l in leaves}
        assert len(bases) == 1, leaves


@pytest.mark.skipif(not _W9_PDF.exists(), reason="w9-heldout form not present")
def test_w9_classification_family_is_one_candidate(tmp_path):
    candidates = gc.find_group_candidates(_dump_for(_W9_PDF, tmp_path))
    groups = _by_leaves(candidates)
    classification = tuple(f"c1_1[{i}]" for i in range(7))
    assert classification in groups
    assert "distinct-on-values" in "; ".join(groups[classification]["signals"])
    # The lone 3b box is NOT a candidate (nothing to group with).
    assert all("c1_2[0]" not in c["leaves"] for c in candidates)


def test_tooltip_prefix_signal_fires_on_tu_key():
    """The dump writes /TU tooltips under "tu" (acroform_dump.py:102); the
    miner must read that key -- reading "tooltip" left the signal permanently
    dead (fresh-eyes finding, bd cqc6; w7/w9 carry no tooltips, so only a
    synthetic dump can pin this)."""
    dump = {"fields": [
        {"name": f"top[0].race_{i}[0]", "logical_type": "checkbox",
         "widgets": [{"on_value": "1", "tu": f"Race. Select all. Option {i}",
                      "rect": {"page": 0, "x": 50.0, "y": 100.0 + 12 * i}}]}
        for i in range(1, 4)
    ]}
    candidates = gc.find_group_candidates(dump)
    assert len(candidates) == 1
    signals = "; ".join(candidates[0]["signals"])
    assert "tooltip-prefix" in signals
    assert "Race. Select all." in signals


def test_render_block_is_suggest_not_decide():
    block = gc.render_candidates_block([
        {"widgets": ["top.c1_2[0]", "top.c1_3[0]"],
         "leaves": ["c1_2[0]", "c1_3[0]"],
         "signals": ["numbered-leaf-run"]},
    ])
    assert "NOT decisions" in block
    assert "ADOPT" in block and "SPLIT" in block
    assert "Never drop a widget" in block
    assert "c1_2[0], c1_3[0]" in block
    # Empty candidates -> empty block (the prompt gains nothing).
    assert gc.render_candidates_block([]) == ""


@pytest.mark.skipif(not _W7_PDF.exists(), reason="w7 kit not present")
def test_build_prompt_flag_gates_the_block(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "arm_llm_native_gc_test", _REPO / "scripts" / "bakeoff" / "arm_llm_native.py")
    arm = importlib.util.module_from_spec(spec)
    sys.modules["arm_llm_native_gc_test"] = arm
    spec.loader.exec_module(arm)

    dump_path = tmp_path / "w7_dump.json"
    acroform_dump.main(["--json", str(dump_path), str(_W7_PDF)])

    off = arm.build_prompt(str(dump_path), None, None, plain=True)
    on = arm.build_prompt(str(dump_path), None, None, plain=True,
                          group_candidates=True)
    assert "GROUP CANDIDATES" not in off  # default OFF
    assert "GROUP CANDIDATES" in on
    assert "c1_2[0], c1_3[0], c1_4[0]" in on  # the reason run is presented
