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
fixed: a NEW cwd-relative "backend/"-prefixed path added to runtime code
fails here instead of being found a review round or a lost log file later.

SCOPE, stated honestly -- this is a static scan, not a proof. It sees a
path BUILT from a leading "backend" literal via Path()/open()/os.path.join,
including f-string and concatenation forms (all pinned by
test_detector_catches_each_path_building_shape below). It does NOT see a
path assembled entirely at runtime (a "backend/..." string read from env or
config, or one built by a helper it cannot follow). Those remain possible;
this closes the shapes anyone is actually likely to write.
"""

import ast
import re
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
# only looks at strings used to BUILD a path.
#
# The shapes checked are deliberately broader than the one that caused this
# bead: a detector that only catches Path("backend/...") lets the identical
# hazard back in as os.path.join("backend", ...), Path(f"backend/{x}"), or
# Path("backend" + x). Those alternates were what a review round found missing
# from the first version of this test, so they are covered explicitly rather
# than trusted not to occur.
# "join" is matched on the bare attribute name, so it catches os.path.join
# without needing to resolve the module -- and would also catch an unrelated
# .join() whose first argument happened to start with "backend". That is a
# false POSITIVE (a spurious CI failure someone must read), never a false
# negative, so it errs in the safe direction; no such call exists today.
_PATH_BUILDERS = {"Path", "open", "join"}

# Bare single-segment literals that are nonetheless cwd-relative PATHS, because
# they name a real top-level directory of this repo. Everything else needs a
# separator to count (see _is_cwd_relative_path).
_REPO_TOP_LEVEL_DIRS = {"backend", "frontend", "logs", "form-kits", "shared"}

# Callables whose LATER argument is a path default rather than a lookup key --
# os.getenv("CONFIRMATION_LOG_DIR", "logs/confirmations") hides a cwd-relative
# path in its second position, which is exactly where confirmation_logger.py
# kept the audit-trail default that a review round found relocated.
_DEFAULT_ARG_READERS = {"getenv", "environ_get", "get"}

# Names that mark a constant as holding a path, for the assignment scan below.
_PATHISH_NAME = re.compile(r"(DIR|PATH|ROOT|FILE|FOLDER|LOG)", re.IGNORECASE)


def _runtime_py_files():
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        if rel.parts and rel.parts[0] in _EXCLUDED_DIRS:
            continue
        yield path


def _is_cwd_relative_path(text: str) -> bool:
    """True for a literal that BUILDS a repo path and resolves against cwd.

    Originally this only matched a leading "backend" segment -- and a review
    round then found confirmation_logger.py writing the audit trail to a bare
    "logs/confirmations", which is the identical hazard with a different first
    word. The invariant is not "no backend/ literals"; it is "no cwd-relative
    path literals", so match on the SHAPE (a relative path with a directory
    separator) rather than on a hard-coded vocabulary of directory names.
    """
    normalized = text.replace("\\", "/")
    if not normalized or normalized.startswith("/") or normalized.startswith("~"):
        return False
    if re.match(r"^[A-Za-z]:", normalized):  # absolute Windows path
        return False
    if normalized.startswith("."):  # ./x and ../x are explicit about cwd
        return False
    # A single bare token ("logs") is usually a name/segment being joined onto
    # an already-anchored base, not a path being resolved -- so a separator is
    # what normally marks a real path. The exception is a known top-level repo
    # directory: "backend" alone IS a cwd-relative path, and it is the one that
    # actually caused this bead.
    if normalized.rstrip("/") in _REPO_TOP_LEVEL_DIRS:
        return True
    return "/" in normalized.rstrip("/")


def _leading_string(node: ast.AST):
    """The literal text a path-building expression STARTS with, if any.

    Only the leading segment matters: it is what decides the resolution base.
    Handles the plain literal, an f-string whose first piece is literal text,
    and a left-nested string concatenation.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # ONLY the first piece matters -- it is what decides the resolution
        # base. If the f-string opens with an interpolation, the base is not a
        # literal and there is nothing here to judge. (Deliberately not a loop:
        # scanning further pieces would find "backend" mid-path, which is not
        # cwd-relative and must not flag -- see the negative case for
        # Path(f"{x}/backend/logs").)
        if not node.values:
            return None
        first = node.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _leading_string(node.left)
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        # os.getenv(KEY, "logs/x") -- the DEFAULT is the path, not the key, so
        # look at the second argument rather than the first.
        if name in _DEFAULT_ARG_READERS and len(node.args) >= 2:
            return _leading_string(node.args[1])
    return None


def _path_shaped_constants(tree: ast.AST):
    """Yield (lineno, literal) for module/class-level NAME = "<relative path>".

    A path literal does not have to sit inside the call that uses it: the
    confirmation-log default lived in a module constant and only reached
    os.getenv() as a variable, so a call-site-only scan saw nothing. Any
    assignment whose name looks path-ish and whose value is a relative path is
    the same hazard one indirection away.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = _leading_string(node.value)
        if value is None or not _is_cwd_relative_path(value):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and _PATHISH_NAME.search(target.id):
                yield node.lineno, value
                break


def _cwd_relative_backend_paths(path: Path):
    """Yield (lineno, literal) for a cwd-relative path in this file.

    Two shapes, because the hazard appears in both:
      1. a path BUILT at a call site -- Path(...)/open(...)/os.path.join(...)
         whose leading argument is a relative path (plain literal, f-string,
         concatenation, a nested call, or an os.getenv default);
      2. a path-shaped CONSTANT assigned a relative literal, which reaches its
         call site as a variable. This is the shape that hid the
         confirmation-log default from the first version of this scan.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    yield from _path_shaped_constants(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name not in _PATH_BUILDERS or not node.args:
            continue
        leading = _leading_string(node.args[0])
        if leading is not None and _is_cwd_relative_path(leading):
            yield node.lineno, leading


@pytest.mark.parametrize(
    "source, should_flag",
    [
        # Shapes that MUST be caught. The first is what actually bit; the rest
        # are the alternates a review round found the first detector missing.
        ('Path("backend/logs")', True),
        ('open("backend/logs/x.txt")', True),
        ('os.path.join("backend", "logs")', True),
        ('Path(os.path.join("backend", "logs"))', True),
        ('Path(f"backend/logs/{x}")', True),
        ('Path(f"backend/{x}/y")', True),
        ('Path("backend" + x)', True),
        ('Path("backend/logs/" + x)', True),
        # NOT "backend"-prefixed, but the identical hazard -- this exact shape
        # (confirmation_logger's audit trail) escaped the first detector.
        ('Path("logs/confirmations")', True),
        ('Path(os.getenv("X", "logs/confirmations"))', True),
        ('open("data/cache/x.json")', True),
        # Shapes that must NOT be flagged -- a detector that fires on these is
        # noise that gets suppressed, which is its own way of going dead.
        # Path("logs") IS cwd-relative -- "logs" is a real top-level dir, so a
        # bare literal here resolves against the process cwd exactly like
        # "logs/confirmations" does. It belongs with the positives.
        ('Path("logs")', True),
        # ...whereas a bare segment that is NOT a top-level repo dir reads as a
        # name being joined onto an already-anchored base, not a path.
        ('Path("audio_out")', False),
        ("Path(x)", False),
        ('Path(f"{x}/backend/logs")', False),
        ('Path(__file__).parent / "backend" / "logs"', False),
        ('Path("/var/run/x")', False),  # absolute
        ('Path("./relative/x")', False),  # explicit about cwd on purpose
        ('json.load("backend/x")', False),  # not a path builder
    ],
)
def test_detector_catches_each_path_building_shape(source, should_flag, tmp_path):
    """Test the test: pin WHICH shapes the scan above can actually see.

    Without this, the scan silently narrows to whatever shape happens to be
    in the tree today, and the guard reads as complete while missing the
    obvious alternates.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import os\nfrom pathlib import Path\nx = 'a'\n" + source + "\n",
        encoding="utf-8",
    )
    hits = list(_cwd_relative_backend_paths(probe))
    assert bool(hits) is should_flag, (
        f"detector {'missed' if should_flag else 'false-positived on'}: {source}"
    )


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
