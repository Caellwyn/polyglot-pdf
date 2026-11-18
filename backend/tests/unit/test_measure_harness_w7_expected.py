"""
Unit tests for the strict W-7 answer key in
scripts/spikes/measure_form_session_costs.py (bd polyglot-pdf-r3ham.14).

Before the key existed every W-7 field scored LENIENT (any non-empty write ==
correct), so a spelled "Ana, A N A" stored as "Anna" counted as a correct fill
on both live models. These tests pin, WITHOUT any live call and WITHOUT naming
a kit field id (CLAUDE.md scar #10):
  - the key covers EXACTLY the W-7 question plan (no field silently falls back
    to lenient scoring, and no stale key outlives a plan edit);
  - score_fill_accuracy scores a wrong spelling as a MISS against an exact key,
    and accepts any member of an any-of key, including an empty decline.

Imports the REAL harness module via sys.path injection (scripts/ carries no
__init__.py), mirroring test_measure_harness_naive_arm.py.

Hermetic: no network, no live model call. ASCII only.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPIKES_DIR = str(_REPO_ROOT / "scripts" / "spikes")
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

import measure_form_session_costs as harness  # noqa: E402


def _client(values: dict):
    return SimpleNamespace(
        state={fid: {"value": v} for fid, v in values.items()},
        schema_fields={})


class TestW7ExpectedCoverage:
    def test_key_covers_exactly_the_w7_plan(self):
        plan_ids = [q["field_id"] for q in harness.W7_QUESTIONS]
        assert plan_ids, "W-7 plan is empty"
        assert set(harness.W7_EXPECTED) == set(plan_ids)

    def test_w7_registry_uses_the_strict_key(self):
        assert harness.SCHEMAS["w7"]["expected"] is harness.W7_EXPECTED

    def test_no_w7_field_scores_lenient(self):
        # Write each key's own expected value; every row must be scored
        # against the key (never 'lenient') and count as correct.
        values = {}
        for fid, exp in harness.W7_EXPECTED.items():
            values[fid] = exp[0] if isinstance(exp, (list, tuple)) else exp
        res = harness.score_fill_accuracy(
            _client(values), harness.W7_QUESTIONS, harness.W7_EXPECTED)
        assert [d["field_id"] for d in res["detail"] if d["scored"] == "lenient"] == []
        assert res["matched"] == res["total"] == len(harness.W7_QUESTIONS)


class TestStrictScoring:
    PLAN = [{"field_id": "synthetic_name"}, {"field_id": "synthetic_declined"}]
    KEY = {"synthetic_name": "Ana", "synthetic_declined": ["", "N/A"]}

    def _ok(self, values):
        res = harness.score_fill_accuracy(_client(values), self.PLAN, self.KEY)
        return {d["field_id"]: d["ok"] for d in res["detail"]}

    def test_wrong_spelling_is_a_miss(self):
        assert self._ok({"synthetic_name": "Anna", "synthetic_declined": ""})["synthetic_name"] is False

    def test_case_and_punctuation_are_ignored(self):
        assert self._ok({"synthetic_name": "ANA.", "synthetic_declined": ""})["synthetic_name"] is True

    def test_any_of_accepts_empty_and_marker(self):
        assert self._ok({"synthetic_name": "Ana", "synthetic_declined": ""})["synthetic_declined"] is True
        assert self._ok({"synthetic_name": "Ana", "synthetic_declined": "n/a"})["synthetic_declined"] is True

    def test_any_of_rejects_a_value(self):
        assert self._ok({"synthetic_name": "Ana", "synthetic_declined": "B2"})["synthetic_declined"] is False
