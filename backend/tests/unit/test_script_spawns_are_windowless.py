"""Every subprocess spawn in scripts/ must suppress its Windows console window.

WHY THIS FILE EXISTS. The maintainer kept seeing terminal windows open and
close with no visible work in them, sometimes escalating into a runaway
cascade that had to be manually stopped.

bd polyglot-pdf-5k32 (PR #205) already diagnosed the mechanism and shipped the
lever: on Windows every subprocess.run of git/bd/dolt opens a visible console
window unless it passes CREATE_NO_WINDOW. But that fix was applied only to the
SessionStart hook scripts that were in the frame at the time. The /closeout
path was missed, and three months later it surfaced as the same cascade --
check_doc_freshness.py alone spawned 263 unprotected git.exe processes per run.

That is scar tissue #8 (CLAUDE.md): the 5k32 fix was CORRECT, it just was not
the whole SET, and the remainder came back one instance at a time. So this
guard pins the SET rather than the instances -- a new unprotected spawn fails
CI instead of resurfacing months later as a window storm.

WHAT THIS CHECKS. Statically (AST -- no subprocess is ever run) every
subprocess.{run,Popen,call,check_output,check_call} call under scripts/ passes
a `creationflags=` keyword. It deliberately does NOT check the VALUE: any
sensible value routes through a windowless_creationflags() helper, and pinning
the literal would just couple the test to a spelling.

SCOPE is derived by EXCLUSION -- every *.py under scripts/, recursively -- so a
new script is covered the day it appears, rather than the day someone
remembers to add it here.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"

SPAWN_ATTRS = {"run", "Popen", "call", "check_output", "check_call"}

# No allowlist. The only spawn that does not pass creationflags= literally is
# beads_remote_bootstrap.run(), which sets it via kw.setdefault() and forwards
# **kw -- already covered by the generic **kwargs exemption below. An explicit
# allowance for it would be redundant today and a silent hole tomorrow, so
# there is deliberately no escape hatch here: if a spawn genuinely cannot take
# the flag, add the case with its reasoning rather than a bare path.


def _iter_spawn_calls():
    """Yield (relpath, lineno, enclosing_func_name, node) for every spawn call."""
    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        # Map each node to its enclosing function so the allowlist can key on
        # a name instead of a line number.
        enclosing: dict[ast.AST, str] = {}
        for func in ast.walk(tree):
            if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(func):
                    enclosing.setdefault(child, func.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not isinstance(fn, ast.Attribute):
                continue
            if fn.attr not in SPAWN_ATTRS:
                continue
            if not (isinstance(fn.value, ast.Name) and fn.value.id == "subprocess"):
                continue
            yield rel, node.lineno, enclosing.get(node, "<module>"), node


def test_every_scripts_spawn_passes_creationflags():
    """No bare subprocess spawn in scripts/ -- the window-storm guard."""
    offenders = []
    for rel, lineno, func, node in _iter_spawn_calls():
        if any(kw.arg == "creationflags" for kw in node.keywords):
            continue
        # **kwargs forwarding counts: the caller supplies the flag.
        if any(kw.arg is None for kw in node.keywords):
            continue
        offenders.append(f"{rel}:{lineno} (in {func}())")

    assert not offenders, (
        "These subprocess spawns do not pass creationflags=, so on Windows each "
        "one opens a visible console window (bd polyglot-pdf-5k32 / "
        "polyglot-pdf-rdftu):\n  "
        + "\n  ".join(offenders)
        + "\n\nPass creationflags=windowless_creationflags() (define the helper "
        "locally, or import swarm_config where its PATH side effect is wanted)."
    )


def test_guard_actually_sees_the_spawn_sites():
    """The guard is scanning real code -- not silently matching nothing.

    Without this, deleting scripts/ or breaking the AST walk would leave the
    test above vacuously green. Pins that the scan finds a substantial set.
    """
    found = list(_iter_spawn_calls())
    assert len(found) >= 25, (
        f"expected the scripts/ tree to contain many subprocess spawns, found "
        f"{len(found)} -- the scanner is probably broken, making the "
        f"creationflags guard vacuous"
    )
