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


def test_every_creationflags_expression_resolves_where_it_is_used():
    """The flag must be RESOLVABLE at the call site, not merely present.

    The guard above pins that `creationflags=` appears. It cannot tell a
    working flag from one that raises at runtime -- and that gap shipped a
    real regression (bd polyglot-pdf-rdftu, caught by the Opus cross-surface
    review): three bootstrap scripts called a module-level
    `windowless_creationflags()` from a function that runs at IMPORT time,
    BEFORE the helper was defined, and whose `subprocess` was function-local.
    Every one raised NameError, which an `except Exception` swallowed -- so
    the spawn was skipped silently and the guard stayed green.

    This checks the two things that make the expression actually work:
      1. if the call site names a helper, that helper is DEFINED ABOVE it
         (module-level def, or an import/alias) -- not merely somewhere in
         the file;
      2. any module-level helper that reads `subprocess` has a module-level
         `import subprocess` to read it from.
    Static, so it needs no import of the scripts (many pull in heavy deps).
    """
    offenders = []
    # Group the spawn sites by file ONCE -- re-walking the whole tree inside
    # the per-file loop made this test take minutes instead of seconds.
    sites_by_file: dict[str, list[tuple[int, str, ast.Call]]] = {}
    for _rel, lineno, func, node in _iter_spawn_calls():
        sites_by_file.setdefault(_rel, []).append((lineno, func, node))

    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))

        # Module-level `import subprocess` (not a function-local one).
        module_imports_subprocess = any(
            isinstance(n, ast.Import)
            and any(a.name == "subprocess" for a in n.names)
            for n in tree.body
        )
        # Where each module-level name becomes usable.
        defined_at: dict[str, int] = {}
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_at.setdefault(n.name, n.lineno)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    defined_at.setdefault(a.asname or a.name.split(".")[0], n.lineno)
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        defined_at.setdefault(t.id, n.lineno)

        # A function that reads `subprocess` must be able to SEE it: either the
        # module imports it, or the function imports it itself. A function-local
        # `import subprocess` is perfectly valid (several bootstrap scripts do
        # it deliberately to keep module import cheap) -- only a function with
        # NEITHER is broken.
        for n in tree.body:
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            reads_subprocess = any(
                isinstance(c, ast.Name) and c.id == "subprocess"
                for c in ast.walk(n)
            )
            imports_it_locally = any(
                isinstance(c, ast.Import)
                and any(a.name == "subprocess" for a in c.names)
                for c in ast.walk(n)
            )
            if reads_subprocess and not (
                module_imports_subprocess or imports_it_locally
            ):
                offenders.append(
                    f"{rel}:{n.lineno} {n.name}() reads `subprocess` but neither "
                    f"the module nor the function imports it"
                )

        for lineno, func, node in sites_by_file.get(rel, ()):
            for kw in node.keywords:
                if kw.arg != "creationflags":
                    continue
                # Only a bare-name helper call needs the ordering check;
                # an inline expression or attribute call carries its own scope.
                if not (isinstance(kw.value, ast.Call)
                        and isinstance(kw.value.func, ast.Name)):
                    continue
                name = kw.value.func.id
                where = defined_at.get(name)
                if where is None:
                    offenders.append(
                        f"{rel}:{lineno} (in {func}()) calls {name}(), which is "
                        f"not defined at module level"
                    )
                elif where > lineno:
                    offenders.append(
                        f"{rel}:{lineno} (in {func}()) calls {name}(), defined "
                        f"LATER at line {where} -- raises NameError if this runs "
                        f"at import time"
                    )

    assert not offenders, (
        "These creationflags expressions are present but cannot resolve where "
        "they are used, so the spawn silently fails or loses the flag "
        "(bd polyglot-pdf-rdftu):\n  " + "\n  ".join(offenders)
    )
