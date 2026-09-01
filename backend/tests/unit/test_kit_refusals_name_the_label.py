"""Every editor refusal names a kit the way the catalogue does (bd kztlr).

THE BUG THIS PINS. A kit has two identities: an `id` (a folder name, usually
auto-generated -- `form`, `form-2`) and a `label` a human gave it ("W-7"). The
catalogue shows the LABEL. Refusals used to name only the ID, so the maintainer
was told deletion had refused "form-2" while no "form-2" appeared anywhere on
screen -- the message could not be matched to the card it was about.

WHY A SET TEST RATHER THAN A FEW EXAMPLES. Fixing the reported instance is what
leaves the next one to be found a review round later (CLAUDE.md scar #8). So
this ENUMERATES every HTTPException detail in the editor routes that names a
kit, derives the list from the shipped source with `ast` rather than a typed
list, and requires each to route through `_kit_name` -- with a short, explicit
allowlist for the two that genuinely cannot.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

from backend.routes.editor_kit_routes import _kit_name

ROUTES_DIR = Path(__file__).resolve().parents[2] / "routes"

# Names that hold a kit identity in these modules.
#
# THIS LIST IS THE DETECTOR'S WEAK POINT, so it is deliberately wider than the
# ids alone. A first version listed only the id-holding names, and was blind to
# `delete_editor_kit` -- the very route the bug was reported on -- because it
# names the kit through a local called `label`. A hand-typed vocabulary catches
# the shapes its author imagined; the assertion below therefore requires the
# CALL, not the absence of a name.
_ID_NAMES = {"kit_id", "superseded_kit", "other_id", "replaces_kit_id",
             "label", "own_label", "other_label", "superseded_label"}

# The ONLY refusals allowed to name a bare id, each because no label exists to
# name. Keyed by (module, function, the detail's leading text) rather than by
# line number, so ordinary edits above them do not need this file updated --
# but ADDING a bare-id refusal does.
_ALLOWED_BARE = {
    # The kit is not in the store, so there is no metadata to read a label from.
    ("editor_kit_routes.py", "_load_meta_or_404", "Unknown kit"),
    # A delete race: the kit was there at the guard and gone at the write.
    # Naming it from the metadata read earlier would assert a label for
    # something that no longer exists.
    ("editor_kit_routes.py", "delete_editor_kit", "Kit not found"),
}


def _detail_head(node: ast.AST) -> str:
    """The literal text a detail starts with, for a stable allowlist key."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            text = child.value.strip()
            if text:
                return text.split("{")[0].split(":")[0].strip()
    return ""


def _bare_id_refusals(path: Path):
    """Every HTTPException detail naming a kit id NOT via _kit_name."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.fn = None
            # Locals in the CURRENT function that already hold a formatted
            # name (`label = _kit_name(kit_id, meta)`). Naming one of those is
            # correct, so the detector follows the assignment rather than
            # flagging the variable -- otherwise widening the vocabulary above
            # just trades a blind spot for a false positive.
            #
            # A name counts as safe only if EVERY assignment to it in the
            # function is from _kit_name. "Assigned safely at least once" is
            # unsound: `label = _kit_name(...)` followed later by
            # `label = kit_id` would mark the name safe forever and let a
            # bare-id refusal through -- and delete_editor_kit uses exactly
            # this assign-then-use shape, so that hole would sit on the route
            # the bug was reported on. This is still flow-INsensitive (it
            # cannot reason about branches), but erring toward flagging is the
            # safe direction for a guard: a false positive is a visible
            # argument, a false negative ships.
            self.safe = set()

        def visit_FunctionDef(self, node):
            prev, prev_safe = self.fn, self.safe
            self.fn = node.name
            self.safe = set()
            safe_names, unsafe_names = set(), set()
            # AugAssign belongs here too: `label += f" ({kit_id})"` MUTATES a
            # safe name back into an unsafe one, and this file's own style
            # already builds messages that way elsewhere. Tracking only
            # rebinding would leave the same hole round 2 closed, reachable
            # through a different node type.
            for n in ast.walk(node):
                if not isinstance(n, (ast.Assign, ast.AnnAssign, ast.For,
                                      ast.AugAssign, ast.NamedExpr)):
                    continue
                targets = (n.targets if isinstance(n, ast.Assign)
                           else [n.target])
                names = {x.id for t in targets for x in ast.walk(t)
                         if isinstance(x, ast.Name)}
                value = getattr(n, "value", None)
                formatted = (isinstance(value, ast.Call)
                             and getattr(value.func, "id", "") == "_kit_name")
                if formatted and isinstance(n, ast.Assign):
                    safe_names |= names
                else:
                    unsafe_names |= names
            # Rebinding through a `with ... as`, `except ... as`, `global` or
            # `nonlocal` is a bind this walk cannot classify, so treat it as
            # unsafe rather than assume: a guard should fail loudly on a shape
            # it does not understand, not stay silent.
            for n in ast.walk(node):
                if isinstance(n, ast.withitem) and n.optional_vars is not None:
                    unsafe_names |= {x.id for x in ast.walk(n.optional_vars)
                                     if isinstance(x, ast.Name)}
                elif isinstance(n, ast.ExceptHandler) and n.name:
                    unsafe_names.add(n.name)
                elif isinstance(n, (ast.Global, ast.Nonlocal)):
                    unsafe_names |= set(n.names)

            # EVERY assignment must be the safe one.
            self.safe = safe_names - unsafe_names
            self.generic_visit(node)
            self.fn, self.safe = prev, prev_safe

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "HTTPException":
                for kw in node.keywords:
                    if kw.arg != "detail":
                        continue
                    wrapped = set()
                    for c in ast.walk(kw.value):
                        if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_kit_name":
                            wrapped |= {
                                x.id for x in ast.walk(c) if isinstance(x, ast.Name)
                            }
                    bare = {
                        x.id for x in ast.walk(kw.value) if isinstance(x, ast.Name)
                    } & _ID_NAMES
                    bare -= wrapped
                    bare -= self.safe
                    if bare:
                        found.append(
                            (path.name, self.fn, _detail_head(kw.value),
                             node.lineno, sorted(bare))
                        )
            self.generic_visit(node)

    V().visit(tree)
    return found


def _editor_route_modules():
    mods = sorted(ROUTES_DIR.glob("editor_*.py"))
    # A finder that silently narrows makes every per-item check vacuous.
    assert len(mods) >= 2, f"expected the editor route modules, found {mods}"
    return mods


def test_every_kit_refusal_names_the_label():
    """No refusal names a bare kit id outside the two that cannot do better."""
    offenders = []
    for mod in _editor_route_modules():
        for name, fn, head, lineno, ids in _bare_id_refusals(mod):
            if (name, fn, head) in _ALLOWED_BARE:
                continue
            offenders.append(f"{name}:{lineno} in {fn}() names {ids} directly")
    assert not offenders, (
        "These refusals name a kit by its internal id, which the human cannot "
        "match to any catalogue card (bd polyglot-pdf-kztlr). Wrap the id in "
        "_kit_name(kit_id, meta):\n  " + "\n  ".join(offenders)
    )


def test_the_allowlist_is_not_stale():
    """Every allowlisted refusal still exists -- an allowlist that names
    nothing real would silently permit a future bare-id refusal that happened
    to land in the same function."""
    live = set()
    for mod in _editor_route_modules():
        for name, fn, head, _ln, _ids in _bare_id_refusals(mod):
            live.add((name, fn, head))
    stale = _ALLOWED_BARE - live
    assert not stale, f"allowlist entries no longer match any refusal: {stale}"


@pytest.mark.parametrize("kit_id,meta,expected", [
    # The maintainer's case: a human-chosen label, so BOTH identities show.
    ("form-2", {"label": "W-7"}, '"W-7" (form-2)'),
    # The catalogue synthesises "Form 2" from `form-2`; showing both would
    # render one fact twice.
    ("form-2", {"label": "Form 2"}, '"form-2"'),
    ("i-90", {"label": "I 90"}, '"i-90"'),
    ("my_form", {"label": "My Form"}, '"my_form"'),
    # A label that starts like the id but adds real words is NOT a restatement.
    ("w7", {"label": "W-7 (ITIN Application)"}, '"W-7 (ITIN Application)" (w7)'),
    # Degraded metadata: fall back to the id rather than inventing a name.
    ("form-2", None, '"form-2"'),
    ("form-2", {}, '"form-2"'),
    ("form-2", {"label": ""}, '"form-2"'),
    ("form-2", {"label": "   "}, '"form-2"'),
    ("form-2", {"label": 17}, '"form-2"'),
])
def test_kit_name_formats(kit_id, meta, expected):
    assert _kit_name(kit_id, meta) == expected


def _unbound_kit_name_args(path: Path):
    """_kit_name calls whose argument is not bound anywhere in the function."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = []

    class V(ast.NodeVisitor):
        def _check(self, fn):
            bound = {a.arg for a in fn.args.args}
            bound |= {a.arg for a in fn.args.kwonlyargs}
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign):
                    for t in n.targets:
                        bound |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
                elif isinstance(n, (ast.AnnAssign, ast.NamedExpr)):
                    bound |= {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}
                elif isinstance(n, ast.For):
                    bound |= {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    bound |= {a.asname or a.name for a in n.names}
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_kit_name":
                    for arg in n.args:
                        if isinstance(arg, ast.Name) and arg.id not in bound:
                            found.append((path.name, n.lineno, fn.name, arg.id))

        def visit_FunctionDef(self, node):
            self._check(node)
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

    V().visit(tree)
    return found


def test_every_kit_name_argument_is_actually_bound():
    """_kit_name(kit_id, meta) with no `meta` in scope is a 500, not a label.

    Found the hard way: the archive route called _load_meta_or_404 and DISCARDED
    its return, so wrapping its 404 in _kit_name raised NameError on the very
    path the wrap was meant to improve -- a refusal turned into a crash.

    The set guard above cannot see this. It asks whether the id is WRAPPED,
    which was true; it cannot ask whether the second argument EXISTS. Routes
    that discard the metadata read are exactly where the next author will reach
    for _kit_name, so this is a likely repeat rather than a one-off.

    LIMIT, stated because a guard that hides one reads as broader assurance
    than it is: this is flow-INSENSITIVE. A name assigned only on a path that
    never executes (`if False:`) counts as bound here and would still raise
    NameError at runtime. Binding a name in dead code is not a shape anyone
    writes on purpose, so the check errs toward silence there; what it catches
    is the shape that actually shipped -- no assignment at all.
    """
    unbound = []
    for mod in _editor_route_modules():
        for name, lineno, fn, arg in _unbound_kit_name_args(mod):
            unbound.append(f"{name}:{lineno} in {fn}() passes unbound '{arg}'")
    assert not unbound, (
        "_kit_name would raise NameError at runtime here. Bind the metadata "
        "(meta, _files = await _load_meta_or_404(...)) rather than discarding "
        "it:\n  " + "\n  ".join(unbound)
    )


# The frontend mirror of _kit_name. The two are hand-written in different
# languages and cannot share code, so the SHARED CONTRACT is pinned instead:
# one table of cases, asserted against both implementations. Reviewers flagged
# the drift risk in two separate rounds; this is what makes the mirroring
# checkable rather than merely asserted in a docstring.
_KITNAME_TS = (
    Path(__file__).resolve().parents[3]
    / "schema-editor" / "src" / "utils" / "kitName.ts"
)

# Every row must render identically on both sides. Keep in sync with the
# parametrized Python cases above -- these ARE those cases, re-run through the
# TypeScript implementation.
_PARITY_CASES = [
    ("form-2", "W-7", '"W-7" (form-2)'),
    ("form-2", "Form 2", '"form-2"'),
    ("i-90", "I 90", '"i-90"'),
    ("my_form", "My Form", '"my_form"'),
    ("w7", "W-7 (ITIN Application)", '"W-7 (ITIN Application)" (w7)'),
    ("form-2", "", '"form-2"'),
    ("form-2", "   ", '"form-2"'),
]


def test_the_typescript_mirror_exists_and_states_the_same_rule():
    """The frontend formatter is present and documents the shared contract.

    A full cross-language parity RUN would need node in the pytest environment,
    which CI does not guarantee for the backend job -- so this pins what can be
    checked from here: the mirror exists, names the backend helper, and encodes
    the same two-branch rule. The behavioural half lives in kitName.test.ts,
    whose cases are the same table as _PARITY_CASES above.

    This is deliberately a WEAK check, and saying so matters: it cannot catch a
    logic divergence, only a disappearance. The real protection is that both
    sides carry the same case table, so a change to one that is not made to the
    other reddens that side's own tests.
    """
    assert _KITNAME_TS.exists(), f"frontend mirror missing: {_KITNAME_TS}"
    src = io.open(_KITNAME_TS, encoding="utf-8").read()
    # It must point back here, or the next author cannot find the other half.
    assert "_kit_name" in src or "editor_kit_routes" in src, (
        "kitName.ts must name its backend counterpart so the mirror is findable"
    )
    # Both branches of the rule must be present.
    assert "labelRestatesId" in src, "the restatement branch is missing"
    assert "${kit.id}" in src, "the bare-id branch is missing"


def test_python_side_matches_the_shared_parity_table():
    """_kit_name agrees with every row of the table kitName.test.ts also uses."""
    for kit_id, label, expected in _PARITY_CASES:
        assert _kit_name(kit_id, {"label": label}) == expected, (
            f"parity row diverged for id={kit_id!r} label={label!r}"
        )
