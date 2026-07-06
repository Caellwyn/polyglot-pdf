"""Tri-state exit semantics for extract_form.py (bd polyglot-pdf-v96b, P5.3a).

The extractor's exit code is the store-with-issues signal the hosted extract
route reads: 0 valid+lint-clean / 3 stored-with-issues / 1 no-usable-draft.
These tests pin _classify_exit's mapping and that the route's mirrored constant
agrees with extract_form.EXIT_ISSUES (the two cannot drift).

Imports extract_form by file path (repo precedent: test_extract_form_lint.py).
ASCII only.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys


_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "extract_form.py"
_spec = importlib.util.spec_from_file_location("extract_form_exit", _SCRIPT)
ef = importlib.util.module_from_spec(_spec)
sys.modules["extract_form_exit"] = ef
_spec.loader.exec_module(ef)


def _draft(fields, valid=True, lint_errors=0):
    return {
        "fields": fields,
        "_bakeoff": {"authoring": {
            "schema_valid": valid,
            "lint": {"errors": lint_errors, "warnings": 0},
        }},
    }


def test_valid_and_lint_clean_is_exit_valid():
    assert ef._classify_exit(_draft([{"id": "a"}])) == ef.EXIT_VALID
    assert ef.EXIT_VALID == 0


def test_zero_fields_is_hard_fail():
    # Below the store-with-issues floor: no usable draft.
    assert ef._classify_exit(_draft([])) == ef.EXIT_HARD_FAIL
    assert ef._classify_exit({"fields": []}) == ef.EXIT_HARD_FAIL
    assert ef.EXIT_HARD_FAIL == 1


def test_non_dict_junk_fields_is_hard_fail():
    # fresh-eyes: a non-empty list of NON-DICT junk (a crash mid-write) is no
    # more usable than an empty list -- it must be HARD_FAIL, not stored-with-
    # issues, matching the route's dict-member floor.
    assert ef._classify_exit({"fields": ["a", "b", 7]}) == ef.EXIT_HARD_FAIL
    assert ef._classify_exit({"fields": "not-a-list"}) == ef.EXIT_HARD_FAIL
    # A mix of one real field + junk IS usable (the real field survives).
    assert ef._classify_exit(_draft([{"id": "a"}, "junk"])) == ef.EXIT_VALID


def test_lint_dirty_but_parseable_is_stored_with_issues():
    got = ef._classify_exit(_draft([{"id": "a"}], valid=True, lint_errors=2))
    assert got == ef.EXIT_ISSUES
    assert ef.EXIT_ISSUES == 3


def test_invalid_but_has_fields_is_stored_with_issues():
    # A draft that fails Pydantic validation but has fields is still storable
    # (the author repairs it in the editor) -- not a hard fail.
    got = ef._classify_exit(_draft([{"id": "a"}], valid=False, lint_errors=0))
    assert got == ef.EXIT_ISSUES


def test_missing_authoring_block_with_fields_is_stored_with_issues():
    # A draft with fields but no provenance block (e.g. schema_valid unknown)
    # is treated as issues, never clean -- clean requires proven valid+clean.
    assert ef._classify_exit({"fields": [{"id": "a"}]}) == ef.EXIT_ISSUES


def test_route_exit_constant_matches_extract_form():
    # The route mirrors EXIT_ISSUES as a literal (it runs the extractor as a
    # subprocess and cannot import the constant); pin them equal so a change to
    # extract_form's exit code cannot silently desync the route's store-with-
    # issues branch.
    import backend.routes.editor_kit_routes as ekr
    assert ekr._EXTRACT_EXIT_ISSUES == ef.EXIT_ISSUES
