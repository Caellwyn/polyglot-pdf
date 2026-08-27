"""Backend runtime file paths must not depend on the process cwd.

The local launchers (scripts/run-schema-editor.sh, scripts/dev-local.ps1) run
uvicorn with backend/ as its WORKING DIRECTORY -- that is what scopes uvicorn's
--reload watch to backend/ instead of the whole repo root, which otherwise
sweeps in .claude/worktrees/ and lets any sibling worktree's edit restart the
local backend (bd polyglot-pdf-b5nmq, after bd polyglot-pdf-nukx2 / PR #650
fixed the same symptom in a way that did not take).

That makes cwd-relative paths a live hazard rather than a theoretical one: a
literal like Path("backend/logs/...") resolved correctly when uvicorn ran from
the repo root and silently resolves to backend/backend/logs/... now.

This pins the SET (CLAUDE.md scar #8), not the individual sites that were
fixed: any NEW cwd-relative "backend/"-prefixed path added to runtime code
fails here instead of being found a review round or a lost log file later.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"

# Directories whose cwd assumptions are an operator's problem, not the served
# app's: tests set their own cwd, and backend/scripts/* are run by hand from
# the repo root.
_EXCLUDED_DIRS = ("tests", "scripts")

# A default ARGUMENT of "backend/..." is allowed only where the receiving code
# demonstrably resolves it against a __file__-derived root rather than the cwd
# (dev_file_logger.DevFileLogger, token_file_logger.TokenFileLogger both do).
# Those are constructor defaults, not path construction, so the check below
# only looks at strings used to BUILD a path -- Path("backend/...") and
# open("backend/...") -- which is the shape that actually resolves against cwd.
_PATH_BUILDERS = {"Path", "open"}


def _runtime_py_files():
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        if rel.parts and rel.parts[0] in _EXCLUDED_DIRS:
            continue
        yield path


def _cwd_relative_backend_paths(path: Path):
    """Yield (lineno, literal) for Path("backend/...")/open("backend/...")."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name not in _PATH_BUILDERS:
            continue
        for arg in node.args:
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                continue
            literal = arg.value
            normalized = literal.replace("\\", "/")
            if normalized == "backend" or normalized.startswith("backend/"):
                yield node.lineno, literal


def test_no_cwd_relative_backend_paths_in_runtime_code():
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}: {literal!r}"
        for path in _runtime_py_files()
        for lineno, literal in _cwd_relative_backend_paths(path)
    ]
    assert not offenders, (
        "These build a path from a cwd-relative 'backend/...' literal. The local "
        "launchers run uvicorn FROM backend/, so each resolves to "
        "backend/backend/... at runtime. Anchor on a __file__-derived root "
        "instead (see _LOG_ROOT in backend/adapters/live_ai_gemini.py):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "module_path, attr",
    [
        ("backend.adapters.live_ai_gemini", "_LOG_ROOT"),
    ],
)
def test_log_roots_are_absolute_and_anchored(module_path, attr):
    """The replacement anchors must be absolute, so cwd cannot affect them."""
    import importlib

    module = importlib.import_module(module_path)
    root = getattr(module, attr)
    assert root.is_absolute(), f"{module_path}.{attr} must be absolute, got {root}"
    assert root == BACKEND / "logs", f"{module_path}.{attr} resolved to {root}"


def test_dev_file_logger_default_log_dir_is_cwd_independent():
    """DevFileLogger's 'backend/logs' default must resolve off __file__."""
    from backend.utils.dev_file_logger import DevFileLogger

    logger = DevFileLogger()
    assert logger.log_dir.is_absolute(), (
        f"DevFileLogger.log_dir must not depend on cwd, got {logger.log_dir}"
    )
    assert logger.log_dir == BACKEND / "logs", (
        f"DevFileLogger.log_dir resolved to {logger.log_dir}"
    )


def test_token_file_logger_default_log_dir_is_cwd_independent():
    """TokenFileLogger already anchors on __file__ -- pin it so it stays that way."""
    from backend.utils.token_file_logger import TokenFileLogger

    logger = TokenFileLogger()
    assert logger.log_file.is_absolute(), (
        f"TokenFileLogger.log_file must not depend on cwd, got {logger.log_file}"
    )
    assert logger.log_file == BACKEND / "logs" / "token_usage.jsonl", (
        f"TokenFileLogger.log_file resolved to {logger.log_file}"
    )
