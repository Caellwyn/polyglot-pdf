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
    # POSIX, relative: `cd backend &&` or `cd backend` on its own line (the
    # form both PDF-debug docs use). Anchored to end-of-line so it cannot be
    # satisfied by "cd backend/some/other/dir".
    re.compile(r"cd\s+backend\s*(?:&&|$)", re.MULTILINE),
    # PowerShell: Set-Location '<root>\backend'
    re.compile(r"Set-Location\s+['\"][^'\"]*\\backend['\"]"),
    # PowerShell: -WorkingDirectory (Join-Path $RepoRoot 'backend')
    re.compile(r"-WorkingDirectory\s+\(Join-Path\s+\$\w+\s+'backend'\)"),
)

# Two spellings of the same launch. dev-local.ps1 builds an ARGUMENT ARRAY
# ('-m', 'uvicorn', 'backend.main:app', ... '--reload') rather than one command
# string, so a single-line regex misses it entirely -- which is exactly what
# test_the_launcher_set_is_non_empty caught when this file was first written.
# Both module spellings: `backend.main:app` (scripts, README) and the bare
# `main:app` used by DEBUG_PDF_FILLING.md / test-pdf-filling.md. Restricting
# this to the dotted form silently drops real members of the set -- those two
# docs are correctly scoped today, so the omission was invisible.
_RELOAD_RE = re.compile(
    r"uvicorn\s+(?:backend\.)?main:app[^\n]*--reload"
    r"|['\"]uvicorn['\"]\s*,\s*['\"](?:backend\.)?main:app['\"]",
    re.IGNORECASE,
)


def _reload_invocations():
    """Yield (path, lineno, segment) for EVERY uvicorn --reload launch.

    One entry per INVOCATION, not per file. A per-file check lets a second,
    unscoped launch in an already-scoped file pass on the strength of the
    first one's `cd` -- which is how a file-wide search stays defeatable no
    matter how strict the cwd pattern itself is.

    `segment` is the text from the END of the previous invocation up to this
    one, so each launch must be preceded by its own cwd statement.
    """
    found = []
    for pattern in _LAUNCHER_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:  # pragma: no cover
                continue
            prev_end = 0
            for match in _RELOAD_RE.finditer(text):
                segment = text[prev_end : match.end()]
                lineno = text.count("\n", 0, match.start()) + 1
                found.append((path, lineno, segment))
                prev_end = match.end()
    return found


def _files_launching_uvicorn_reload():
    return sorted({path for path, _, _ in _reload_invocations()})


def test_the_launcher_set_is_non_empty():
    """Guard the guard: if the discovery pattern silently stops matching, the
    per-launcher test below would vacuously pass with nothing to check."""
    # Bare Paths, NOT (path, text) pairs -- unpacking as a 2-tuple here raised
    # TypeError instead of printing the diagnostic, and only a TOTAL discovery
    # failure hid it (an empty generator never iterates). A partial regression,
    # which is the likely one, would have lost the message it exists to give.
    found = _files_launching_uvicorn_reload()
    rendered = ", ".join(p.relative_to(REPO_ROOT).as_posix() for p in found)
    assert len(found) >= 5, (
        "expected to discover the known uvicorn --reload launcher FILES "
        "(dev-local.sh, dev-local.ps1, dev_env.ps1, start-token-monitor.sh, "
        "README.md, DEBUG_PDF_FILLING.md, test-pdf-filling.md); found "
        f"{len(found)}: {rendered}"
    )


# PowerShell's Start-Process takes the cwd as an ARGUMENT, so dev-local.ps1
# builds its uvicorn arg-array first and only names the working directory ~80
# lines later. That one construct is therefore allowed to appear after the
# launch; every other dialect must set the cwd BEFORE it. Kept as its own
# pattern rather than a lookahead window so nothing else gets the exemption.
_TRAILING_CWD_PATTERN = re.compile(
    r"-WorkingDirectory\s+\(Join-Path\s+\$\w+\s+'backend'\)"
)


@pytest.mark.parametrize(
    "path, lineno, segment",
    _reload_invocations(),
    # id from path+lineno only -- the segment is whole file chunks, and letting
    # it into the id makes failures unreadable.
    ids=[
        f"{p.relative_to(REPO_ROOT).as_posix()}:{n}"
        for p, n, _ in _reload_invocations()
    ],
)
def test_reload_launcher_runs_from_backend(path, lineno, segment):
    """Each INVOCATION must be preceded by its own cwd-setting statement.

    Checking per-file instead lets a second, unscoped launch in the same file
    pass on the first one's `cd`; checking a proximity window instead either
    misses the cwd (it can sit ~80 lines away) or sweeps in kill/cleanup
    blocks that merely name backend paths. Segment = since the previous
    invocation, so evidence cannot be reused across launches.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    scoped = any(pat.search(segment) for pat in _CWD_PATTERNS) or (
        _TRAILING_CWD_PATTERN.search(text) is not None
    )
    assert scoped, (
        f"{path.relative_to(REPO_ROOT)}:{lineno} starts `uvicorn --reload` but "
        "does not establish backend/ as the working directory first. uvicorn "
        "DISCARDS a --reload-dir nested inside the process cwd and watches the "
        "cwd instead, so this will watch the whole repo -- including "
        ".claude/worktrees/ -- and restart on unrelated agent edits. "
        "Run uvicorn from backend/ (see scripts/run-schema-editor.sh)."
    )
