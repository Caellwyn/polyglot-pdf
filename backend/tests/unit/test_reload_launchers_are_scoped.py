"""Every `uvicorn --reload` launcher must be scoped to backend/ (bd polyglot-pdf-b5nmq).

uvicorn's WatchFiles supervisor DROPS any --reload-dir that is a CHILD of the
process cwd and watches the cwd instead. So a launcher that starts from the
repo root watches the WHOLE tree -- including .claude/worktrees/ and its ~130
sibling checkouts, where an edit by any agent restarts the developer's backend
mid-request. The only arrangement uvicorn actually honors is cwd == the reload
dir.

This pins the SET, not the instances (CLAUDE.md scar #8). The bug was fixed
three separate times in this repo before anyone enumerated the launchers:
PR #650 fixed one, bd b5nmq fixed two more, and the enumeration for THIS test
turned up a fourth (scripts/dev_env.ps1) plus the README's onboarding command
that nobody had looked at. A new launcher that starts uvicorn --reload from
the repo root now fails here instead of being discovered as a mystery restart
months later.

The check is textual because these are shell/PowerShell/markdown, not Python:
find the launch command, then require the same file establishes backend/ as
the working directory.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Files that launch uvicorn with --reload. Enumerated by grepping the repo for
# "uvicorn" across scripts, docs and container files; archived/historical docs
# under docs/archive and planning_documents are excluded as non-operational.
_LAUNCHER_GLOBS = ("scripts/*.sh", "scripts/*.ps1", "*.md", "scripts/*.md")

# The cwd-setting STATEMENT in each dialect -- a command that actually changes
# the working directory to backend/, not merely a string containing "backend".
#
# Anchoring on the construct is what makes this checkable. The looser forms
# both failed: a bare "cd backend" substring matched unrelated README prose
# 300 lines from the launch, and a proximity window around the launch line
# could not span dialects that put the cwd on opposite sides of it without
# also swallowing the kill/cleanup blocks.
_CWD_PATTERNS = (
    # POSIX: cd "<root>/backend"  (subshell or standalone)
    re.compile(r"""cd\s+["']?\$\{?(?:REPO_ROOT|ROOT_DIR)\}?/backend["']?"""),
    # POSIX, relative: cd backend && <launch>
    re.compile(r"cd\s+backend\s*&&"),
    # PowerShell: Set-Location '<root>\backend'
    re.compile(r"Set-Location\s+['\"][^'\"]*\\backend['\"]"),
    # PowerShell: -WorkingDirectory (Join-Path $RepoRoot 'backend')
    re.compile(r"-WorkingDirectory\s+\(Join-Path\s+\$\w+\s+'backend'\)"),
)

# Two spellings of the same launch. dev-local.ps1 builds an ARGUMENT ARRAY
# ('-m', 'uvicorn', 'backend.main:app', ... '--reload') rather than one command
# string, so a single-line regex misses it entirely -- which is exactly what
# test_the_launcher_set_is_non_empty caught when this file was first written.
_RELOAD_RE = re.compile(
    r"uvicorn\s+backend\.main:app[^\n]*--reload"
    r"|['\"]uvicorn['\"]\s*,\s*['\"]backend\.main:app['\"]",
    re.IGNORECASE,
)


def _files_launching_uvicorn_reload():
    seen = []
    for pattern in _LAUNCHER_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:  # pragma: no cover
                continue
            if _RELOAD_RE.search(text):
                seen.append((path, text))
    return seen


def test_the_launcher_set_is_non_empty():
    """Guard the guard: if the discovery pattern silently stops matching, the
    per-launcher test below would vacuously pass with nothing to check."""
    found = _files_launching_uvicorn_reload()
    assert len(found) >= 4, (
        "expected to discover the known uvicorn --reload launchers "
        "(dev-local.sh, dev-local.ps1, dev_env.ps1, README.md); found: "
        + ", ".join(str(p.relative_to(REPO_ROOT)) for p, _ in found)
    )


@pytest.mark.parametrize(
    "path, text",
    _files_launching_uvicorn_reload(),
    ids=lambda v: str(v.relative_to(REPO_ROOT)) if isinstance(v, Path) else "",
)
def test_reload_launcher_runs_from_backend(path, text):
    # Evidence region = the launch command and the few lines leading into it,
    # NOT the whole file. A file-wide search reads unrelated prose as proof:
    # README.md's "cd backend" 300 lines below the launch block satisfied this
    # check even with the cd stripped OUT of the launch line itself.
    # Match the CONSTRUCT that sets the cwd, not text near the launch line.
    # A proximity window cannot work here: the shell scripts `cd` before the
    # launch, dev-local.ps1 passes -WorkingDirectory ~80 lines after it, and
    # every window wide enough to catch the latter also swept in the kill and
    # cleanup blocks (which name backend paths) and passed a mutated file.
    # Each pattern below is the actual cwd-setting statement, anchored so it
    # cannot be satisfied by an unrelated mention of the word "backend".
    assert any(pat.search(text) for pat in _CWD_PATTERNS), (
        f"{path.relative_to(REPO_ROOT)} starts `uvicorn --reload` but does not "
        "establish backend/ as the working directory. uvicorn DISCARDS a "
        "--reload-dir nested inside the process cwd and watches the cwd "
        "instead, so this will watch the whole repo -- including "
        ".claude/worktrees/ -- and restart on unrelated agent edits. "
        "Run uvicorn from backend/ (see scripts/run-schema-editor.sh)."
    )
