"""The derive-BEFORE-repair step ordering in extract_form's pipeline.

bd polyglot-pdf-kow7. `tests/test_extract_form_sections.py` exercises
`derive_and_apply` and `_repair_schema` in the order `extract()` happens to
call them, but it never invokes `extract()` itself -- its own docstrings say
so plainly ("it does NOT detect a future refactor that REORDERS the
pipeline"). So the ordering the pipeline depends on was unguarded.

AND THAT FILE IS DEAD IN CI ANYWAY. All 11 of its cases are gated on a real
checked-in kit (`w7 kit not present`, `f1040 kit not present`,
`form-kits/i-90/form.pdf not present`), and NO kit is tracked in git by
design (CLAUDE.md scar #10). They skip in CI, so even the composition
properties they do assert are only checked on a maintainer's machine that
happens to have a kit lying around. A guard for the ordering therefore had
to need no kit at all.

WHY STATIC. `derive_and_apply` wants a real PDF on disk, so a runtime test of
the ordering needs a fixture kit -- exactly the dependency that makes the
existing file inert. Reading the SOURCE needs nothing, runs everywhere, and
the property is genuinely syntactic: which call comes first inside
`extract()`. Repo precedent for AST-based pins: `tests/test_llm_providers.py`,
`backend/tests/unit/test_bootstrap_editor_message.py`.

WHY THE ORDER MATTERS (from extract_form.py's own step comments): step 3e
derivation re-files EVERY field into derived divisions, and step 4 repair
fixes up references against the schema it is handed. Repairing first means
repair operates on the PRE-derivation section layout and derivation then
overwrites the section ids repair just reconciled -- so repair's work is
discarded and any reference it would have fixed is silently re-broken.

ASCII only.
"""

import ast
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "authoring" / "extract_form.py"

# The two pipeline steps, by the callee name as written in the source.
_DERIVE = "derive_and_apply"
_REPAIR = "_repair_schema"


def _callee_name(node: ast.AST) -> str | None:
    """The called name for `f(...)` and `mod.f(...)`, else None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_fn() -> ast.FunctionDef:
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"), filename=str(_SCRIPT))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "extract":
            return node
    pytest.fail(
        f"extract() not found in {_SCRIPT.name} -- if the pipeline entry point "
        "was renamed, update this test to the new name rather than deleting it."
    )


def _call_lines(fn: ast.FunctionDef, name: str) -> list[int]:
    return sorted(
        node.lineno
        for node in ast.walk(fn)
        if _callee_name(node) == name
    )


def test_extract_calls_derive_before_repair():
    """The pin. A reorder inside extract() fails HERE, with no kit required."""
    fn = _extract_fn()
    derive = _call_lines(fn, _DERIVE)
    repair = _call_lines(fn, _REPAIR)

    # Non-vacuity: if either call disappears or is renamed, this must fail
    # loudly rather than pass on an empty comparison -- the failure mode that
    # makes a "green" ordering test worthless.
    assert derive, (
        f"no call to {_DERIVE}() inside extract() -- the ordering this test "
        "pins no longer exists as written; re-point it at the real step."
    )
    assert repair, (
        f"no call to {_REPAIR}() inside extract() -- the ordering this test "
        "pins no longer exists as written; re-point it at the real step."
    )

    assert max(derive) < min(repair), (
        f"extract() must call {_DERIVE}() (step 3e) BEFORE {_REPAIR}() "
        f"(step 4). Found {_DERIVE} at {derive} and {_REPAIR} at {repair}. "
        "Derivation re-files every field into derived divisions, so repairing "
        "first means repair reconciles references against the PRE-derivation "
        "layout and derivation then overwrites the section ids it just fixed."
    )


def test_each_step_is_called_exactly_once_in_extract():
    """A second call to either step would make 'which comes first' ambiguous.

    Without this, someone could ADD an early `_repair_schema(...)` and leave
    the original late one in place: `max(derive) < min(repair)` would then be
    False and the pin above would fire -- but the reverse shape (an extra
    LATE derive) would still pass while the pipeline had genuinely changed.
    Pinning the count makes the ordering assertion unambiguous in both
    directions.
    """
    fn = _extract_fn()
    for name in (_DERIVE, _REPAIR):
        lines = _call_lines(fn, name)
        assert len(lines) == 1, (
            f"expected exactly 1 call to {name}() inside extract(), found "
            f"{len(lines)} at {lines}. If a second call is deliberate, decide "
            "which one the ordering contract is about and say so here."
        )
