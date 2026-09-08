"""Every MUTATING admin route audits, in the form its mutation REQUIRES
(bd polyglot-pdf-li9x0).

WHAT THIS IS NOT. It is not "some audit call is present". The plan is
explicit that the two forms are not interchangeable, and asserting mere
presence would pass a Firestore mutation that audits fire-and-forget outside
its transaction -- exactly the double-apply window the log exists to close.
So this file derives, per route, WHICH form is required and checks for THAT
one:

  * MUTATION_KIND_FIRESTORE -> audit_log.record_in_transaction must be
    called, and it must be called INSIDE a @firestore.transactional body
    (a call outside one is not in the mutation's transaction, whatever it
    is named).
  * MUTATION_KIND_EXTERNAL  -> audit_log.record_pending must be called, AND
    at least one of mark_committed / mark_failed must close the row out.
    A pending row nothing ever closes is worse than no row: every action
    would look half-applied forever.

HOW THE ROUTE SET IS DERIVED. Off the LIVE app object (app.routes), like
test_admin_route_auth.py -- never a hand-kept list, so a route added without
an audit call fails HERE instead of shipping unaudited. Each mutating route
must appear in MUTATION_KINDS, which is the ONE place a route's required
form is declared; a new mutating route with no entry fails too, so the
declaration cannot be skipped by silence.

WHY AST AND NOT A RUNTIME PROBE. Driving every mutating route with a real
request would need a working fake for whatever each one mutates (Firebase
Auth, Cloud Build), and that scaffolding is what rots. The structural
question -- does this handler's module reach a call to the required helper,
in the required position -- is answerable statically and stays answerable as
the routes multiply.

ASCII only.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from admin_backend.main import app

# The methods that can change state. GET and HEAD cannot, and OPTIONS is
# CORS preflight.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

MUTATION_KIND_FIRESTORE = "firestore"
MUTATION_KIND_EXTERNAL = "external"

# THE DECLARATION. Every mutating route on this service, and which audit form
# its mutation requires. Keyed by (method, path) exactly as FastAPI registers
# it -- the same shape test_admin_route_auth.py's route-set pin uses.
#
# A route lands here in the SAME commit that adds it. Epic 2's B-track adds
# the firm/credit/kit routes (all firestore); Epic 1's user routes and Epic
# 4's build triggers are external.
MUTATION_KINDS = {
    ("PUT", "/admin/config/{channel}"): MUTATION_KIND_FIRESTORE,
}

# The helper names each form requires, by kind.
_REQUIRED_CALLS = {
    MUTATION_KIND_FIRESTORE: ("record_in_transaction",),
    MUTATION_KIND_EXTERNAL: ("record_pending",),
}
_CLOSEOUT_CALLS = ("mark_committed", "mark_failed")


def _mutating_routes():
    """(method, path, endpoint) for every state-changing route on the app."""
    found = []
    for route in app.routes:
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or endpoint is None:
            continue
        for method in sorted(getattr(route, "methods", None) or []):
            if method in MUTATING_METHODS:
                found.append((method, path, endpoint))
    return found


def _module_tree(endpoint):
    """The parsed AST of the module the handler is defined in.

    The MODULE, not just the handler function: a route that delegates its
    write to a module-level helper (which is exactly what
    config_routes._apply_config_write does, because a @firestore.transactional
    body needs its own function) would otherwise look unaudited.
    """
    source_file = inspect.getsourcefile(endpoint)
    assert source_file, "cannot locate source for {!r}".format(endpoint)
    text = pathlib.Path(source_file).read_text(encoding="utf-8")
    return ast.parse(text), source_file


def _called_names(node) -> set:
    """Every function name called anywhere under `node`.

    Collects the bare attribute/name, so `audit_log.record_in_transaction(...)`
    and a `from ... import record_in_transaction` call both register. Matching
    on the bare name is deliberate: the alias a module imports under is not
    the contract; the helper it reaches is.
    """
    names = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return names


def _is_transactional(func_node) -> bool:
    """True when this function carries the @firestore.transactional decorator.

    Matched on the decorator's ATTRIBUTE name (transactional), not the full
    dotted path, because the module imports firebase_admin.firestore lazily
    inside the enclosing function -- the name it is bound to locally is not
    part of the contract.
    """
    for dec in getattr(func_node, "decorator_list", []):
        if isinstance(dec, ast.Attribute) and dec.attr == "transactional":
            return True
        if isinstance(dec, ast.Name) and dec.id == "transactional":
            return True
    return False


def _calls_inside_transactional_bodies(tree) -> set:
    """Every name called inside SOME @firestore.transactional function.

    This is the check that gives the Firestore form its teeth: a module can
    call record_in_transaction from anywhere, but only a call inside a
    transactional body is actually in the mutation's transaction.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                _is_transactional(node):
            names |= _called_names(node)
    return names


def test_every_mutating_route_declares_its_required_audit_form():
    """A new mutating route must SAY which form it needs.

    Without this, an unaudited route could slip through by simply not
    appearing in MUTATION_KINDS -- the coverage test would then iterate over
    a set that quietly excludes it. Mutation: register a POST route and do
    not add it here -- red."""
    undeclared = [
        (method, path) for method, path, _ in _mutating_routes()
        if (method, path) not in MUTATION_KINDS
    ]
    assert not undeclared, (
        "these mutating admin routes do not declare an audit form in "
        "MUTATION_KINDS: {}. Every state-changing route audits; add each "
        "with the form its mutation requires (firestore -> "
        "record_in_transaction inside the mutation's transaction; external "
        "-> record_pending then mark_committed/mark_failed).".format(
            sorted(undeclared)))


def test_the_declaration_names_no_route_that_does_not_exist():
    """The reverse direction: a stale entry for a deleted route would make
    the coverage below silently assert nothing about a route that is gone,
    and would hide the fact that the real one is missing."""
    live = {(m, p) for m, p, _ in _mutating_routes()}
    stale = set(MUTATION_KINDS) - live
    assert not stale, (
        "MUTATION_KINDS names routes the app does not register: {}".format(
            sorted(stale)))


@pytest.mark.parametrize(
    "method,path",
    sorted(MUTATION_KINDS),
    ids=["{} {}".format(m, p) for m, p in sorted(MUTATION_KINDS)],
)
def test_a_mutating_route_uses_the_audit_form_its_mutation_requires(
        method, path):
    """THE COVERAGE PIN, one parametrization per mutating route.

    Mutation (Firestore routes): delete the record_in_transaction call from
    config_routes._apply_config_write -- red. Move that call OUT of the
    @firestore.transactional body into the enclosing function -- ALSO red,
    which is the half a presence check would miss.

    Mutation (external routes, once one exists): delete record_pending --
    red; delete both mark_committed and mark_failed -- red.
    """
    endpoint = next(e for m, p, e in _mutating_routes()
                    if (m, p) == (method, path))
    kind = MUTATION_KINDS[(method, path)]
    tree, source_file = _module_tree(endpoint)

    module_calls = _called_names(tree)
    for required in _REQUIRED_CALLS[kind]:
        assert required in module_calls, (
            "{} {} is a {} mutation but {} never calls "
            "audit_log.{}".format(method, path, kind, source_file, required))

    if kind == MUTATION_KIND_FIRESTORE:
        in_tx = _calls_inside_transactional_bodies(tree)
        assert "record_in_transaction" in in_tx, (
            "{} {} calls audit_log.record_in_transaction, but NOT inside a "
            "@firestore.transactional body in {} -- an audit row outside the "
            "mutation's transaction can commit while the mutation fails (or "
            "the reverse), which is the double-apply window the "
            "in-transaction form exists to close.".format(
                method, path, source_file))
        # And the mutation itself must be in there with it: a transactional
        # body carrying ONLY the audit row would pass the check above while
        # the real write sat outside.
        assert "set" in in_tx or "update" in in_tx or "delete" in in_tx, (
            "{} {}'s @firestore.transactional body writes nothing -- the "
            "audit row is inside a transaction the mutation is not in".format(
                method, path))
    else:
        assert any(name in module_calls for name in _CLOSEOUT_CALLS), (
            "{} {} writes a pending audit row but never closes it out with "
            "mark_committed or mark_failed in {} -- every action would look "
            "half-applied forever.".format(method, path, source_file))


# --------------------------------------------------------------------------
# Proving the coverage test is not vacuous, BOTH WAYS (exit criterion 2).
# --------------------------------------------------------------------------

_FIRESTORE_ROUTE_OK = """
from firebase_admin import firestore
from admin_backend.services import audit_log

def handler():
    @firestore.transactional
    def _txn(tx):
        tx.set(ref, {})
        audit_log.record_in_transaction(tx, db)
    _txn(db.transaction())
"""

_FIRESTORE_ROUTE_NO_AUDIT = """
from firebase_admin import firestore

def handler():
    @firestore.transactional
    def _txn(tx):
        tx.set(ref, {})
    _txn(db.transaction())
"""

_FIRESTORE_ROUTE_AUDIT_OUTSIDE_TX = """
from firebase_admin import firestore
from admin_backend.services import audit_log

def handler():
    @firestore.transactional
    def _txn(tx):
        tx.set(ref, {})
    _txn(db.transaction())
    audit_log.record_in_transaction(None, db)
"""

_EXTERNAL_ROUTE_OK = """
from admin_backend.services import audit_log

def handler():
    ref = audit_log.record_pending(db)
    do_the_auth_thing()
    audit_log.mark_committed(ref)
"""

_EXTERNAL_ROUTE_NO_PENDING = """
def handler():
    do_the_auth_thing()
"""

_EXTERNAL_ROUTE_NEVER_CLOSED = """
from admin_backend.services import audit_log

def handler():
    audit_log.record_pending(db)
    do_the_auth_thing()
"""


def _firestore_verdict(source: str) -> bool:
    """The SAME two checks the Firestore branch above applies."""
    tree = ast.parse(source)
    module_calls = _called_names(tree)
    if "record_in_transaction" not in module_calls:
        return False
    in_tx = _calls_inside_transactional_bodies(tree)
    if "record_in_transaction" not in in_tx:
        return False
    return bool({"set", "update", "delete"} & in_tx)


def _external_verdict(source: str) -> bool:
    """The SAME two checks the external branch above applies."""
    tree = ast.parse(source)
    module_calls = _called_names(tree)
    if "record_pending" not in module_calls:
        return False
    return any(name in module_calls for name in _CLOSEOUT_CALLS)


@pytest.mark.parametrize("source,expected,why", [
    (_FIRESTORE_ROUTE_OK, True, "the correct in-transaction form"),
    (_FIRESTORE_ROUTE_NO_AUDIT, False, "no audit call at all"),
    (_FIRESTORE_ROUTE_AUDIT_OUTSIDE_TX, False,
     "audits, but OUTSIDE the mutation's transaction"),
])
def test_the_firestore_check_goes_red_on_a_dropped_in_transaction_call(
        source, expected, why):
    """EXIT CRITERION 2, direction one. Runs the real derivation against
    hand-built route shapes: a Firestore route that drops the in-transaction
    call, and -- the case a presence check would wave through -- one that
    audits outside the transaction."""
    assert _firestore_verdict(source) is expected, why


@pytest.mark.parametrize("source,expected,why", [
    (_EXTERNAL_ROUTE_OK, True, "the correct pending-then-committed form"),
    (_EXTERNAL_ROUTE_NO_PENDING, False, "no pending row at all"),
    (_EXTERNAL_ROUTE_NEVER_CLOSED, False,
     "a pending row nothing ever closes out"),
])
def test_the_external_check_goes_red_on_a_skipped_pending_row(
        source, expected, why):
    """EXIT CRITERION 2, direction two. The external form has no consuming
    route yet (Epic 1's user routes and Epic 4's build triggers are its first
    consumers), so its check is proven against the same synthetic shapes
    rather than shipped untested -- the same reasoning
    test_admin_route_auth.py applies to the three gates that do not exist
    yet."""
    assert _external_verdict(source) is expected, why


def test_the_shipped_config_route_passes_the_synthetic_firestore_check():
    """Ties the synthetic proofs above to the REAL module.

    Without this, the checks could be proven against toy sources while the
    live derivation ran different code. Same function, real file."""
    from admin_backend.routes import config_routes

    source = pathlib.Path(
        inspect.getsourcefile(config_routes)).read_text(encoding="utf-8")
    assert _firestore_verdict(source), (
        "config_routes.py does not satisfy the same in-transaction check the "
        "synthetic cases are graded against")
