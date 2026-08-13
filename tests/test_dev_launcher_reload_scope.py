"""Every dev launcher that starts uvicorn with --reload must SCOPE the watcher.

Why this test exists (bd polyglot-pdf-tqr3c). A bare `--reload` watches the whole
cwd tree. All of these launchers run uvicorn from the REPO ROOT, and the repo root
holds `.claude/worktrees/` -- on the maintainer's machine, ~130 full checkouts. So
an agent editing any .py in ANY sibling worktree restarted the backend. In the
schema editor that also killed the in-flight, minutes-long POST /api/extract
(run-schema-editor.sh runs under `set -e` with a teardown trap, so the backend's
exit tore down Vite too), and the browser reported it as a bare "Failed to fetch".

This pins the SET, not the instances. The first fix covered only run-schema-
editor.sh and dev-local.ps1; a reviewer found dev-local.sh, and enumerating
properly then turned up start_backend.bat as well -- the exact "fixed one member
of a set" trap in CLAUDE.md scar tissue #7. So the launcher list is DERIVED by
scanning scripts/ rather than hand-listed: a new launcher, or a fixed one that
regresses to a bare --reload, fails here instead of costing a review round.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Files whose uvicorn mention is ECHOED HELP TEXT, not an invocation. These print
# a suggested command for the reader; they never spawn a server, so there is no
# watcher to scope. Listed explicitly so that a real launcher can never be waved
# through by accident -- adding a name here is a deliberate, reviewable act.
_NOT_INVOCATIONS = {
    "start-token-monitor.sh",
    "start-token-monitor.bat",
}


def _launcher_lines() -> list[tuple[Path, str]]:
    """Every line in scripts/ that actually LAUNCHES uvicorn with --reload.

    Derived, never hand-listed -- that is the whole point of this test.
    """
    hits: list[tuple[Path, str]] = []
    for path in sorted(SCRIPTS_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in {".sh", ".ps1", ".bat"}:
            continue
        if path.name in _NOT_INVOCATIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # Normalize a whole invocation onto ONE logical line before scanning.
        # Two shapes need joining, and missing either makes this scan blind:
        #   - shell/PowerShell line continuations (`\` and backtick):
        #     run-schema-editor.sh splits its uvicorn call that way.
        #   - a PowerShell ARGUMENT ARRAY: dev-local.ps1 builds
        #     $BackendArgs = @('-m','uvicorn','backend.main:app',...,'--reload',
        #     '--reload-dir','backend'), so the flags live on separate lines
        #     inside @( ... ) with no continuation character at all.
        # The array case is why the companion scan-integrity test exists: the
        # first version of this helper silently missed dev-local.ps1 entirely.
        # Strip whole-line comments BEFORE joining. Order matters: an argument
        # array can carry an explanatory comment BETWEEN two flags, and joining
        # first would let that comment swallow every argument after it on the
        # flattened line (this bit -- dev-local.ps1 documents its --reload-dir on
        # the line above the flag itself).
        decommented = "\n".join(
            "" if ln.strip().startswith(("#", "REM ", "rem ", "echo ")) else ln
            for ln in text.splitlines()
        )
        joined = re.sub(r"[\\`]\s*\n\s*", " ", decommented)
        joined = re.sub(r"@\(\s*(.*?)\s*\)", lambda m: m.group(1).replace("\n", " "),
                        joined, flags=re.DOTALL)
        for line in joined.splitlines():
            if "uvicorn" not in line or "--reload" not in line:
                continue
            hits.append((path, line))
    return hits


def test_the_scan_finds_the_known_launchers() -> None:
    """Guard the DERIVATION itself.

    Without this, a scanner bug that silently matched nothing would make every
    other assertion in this file vacuously pass -- the classic way a set-pinning
    test rots into a no-op.
    """
    found = {path.name for path, _ in _launcher_lines()}
    # These four are the known reload-launchers at the time of writing. New ones
    # are welcome (the parametrized test below covers them automatically); this
    # only asserts the scan has not gone blind to the ones we know exist.
    expected = {
        "dev-local.ps1",
        "dev-local.sh",
        "dev_env.ps1",
        "run-schema-editor.sh",
        "start_backend.bat",
    }
    missing = expected - found
    assert not missing, (
        f"the launcher scan no longer sees {sorted(missing)} -- the scan is "
        f"broken, so every other assertion here is vacuous. Found: {sorted(found)}"
    )


@pytest.mark.parametrize(
    "path,line",
    _launcher_lines(),
    ids=lambda v: v.name if isinstance(v, Path) else "",
)
def test_reload_watcher_is_scoped(path: Path, line: str) -> None:
    """A --reload launcher must also pass --reload-dir (or --reload-exclude)."""
    assert "--reload-dir" in line or "--reload-exclude" in line, (
        f"{path.relative_to(REPO_ROOT)} starts uvicorn with a bare --reload:\n"
        f"    {line.strip()}\n"
        "A bare --reload watches the WHOLE cwd tree, which here includes "
        "`.claude/worktrees/` (~130 sibling checkouts) -- an agent editing a .py "
        "in ANY of them will restart this backend and drop in-flight requests. "
        "Add `--reload-dir backend` (see bd polyglot-pdf-tqr3c)."
    )
