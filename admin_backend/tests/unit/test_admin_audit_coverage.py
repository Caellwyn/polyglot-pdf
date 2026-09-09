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
    IN THIS SAME MODULE (a call outside one is not in the mutation's
    transaction, whatever it is named) -- OR, for a route whose Firestore
    transaction is opened by ANOTHER module's helper (bd polyglot-pdf-zopqq's
    credit_routes.py joining backend/services/credit_ledger.py's
    append_entry; bd polyglot-pdf-8vgfh's sweep route joining that same
    module's refund_expired_link), inside a closure passed BY NAME as an
    extra_writes= keyword argument at a call site in the SAME module to one
    of _EXTRA_WRITES_TRANSACTION_OPENERS. extra_writes is this repo's one
    documented seam for joining a second write to a transaction someone else
    opened (both helpers take it, with the identical contract: called (tx,
    firm_snapshot) from INSIDE the body, after the reads); a closure that is
    never handed to extra_writes= is just a function sitting unused,
    whatever it contains. The GENUINE in-transaction guarantee (does the
    callback actually run before commit, atomically with the mutation) is
    proven by a real test exercising the real call path, not by AST alone --
    see test_sweep_routes.py::test_a_forced_audit_failure_leaves_the_refund_
    uncommitted and test_credit_routes.py's sibling, the extra_writes shape's
    equivalent of the plain-transactional kind's own "forced audit failure
    leaves the mutation unapplied" pin.
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
    # Firebase Auth mutations (bd polyglot-pdf-dmjl5). EXTERNAL, and not by
    # choice: there is no Firestore transaction for an auth.create_user or a
    # set_custom_user_claims to join, so the pending-then-committed form is
    # the only one available.
    ("POST", "/admin/users"): MUTATION_KIND_EXTERNAL,
    ("PATCH", "/admin/users/{uid}/disable"): MUTATION_KIND_EXTERNAL,
    ("PATCH", "/admin/users/{uid}/role"): MUTATION_KIND_EXTERNAL,
    # Firm CRUD + credit grant/adjust (bd polyglot-pdf-zopqq). All FIRESTORE:
    # every one is a firms/{firm_id} or firms/{firm_id}/ledger write, audited
    # inside the SAME @firestore.transactional body as the mutation
    # (firm_routes.py's _apply_firm_patch / create_firm; credit_routes.py's
    # _run_append_entry, joined to credit_ledger.append_entry's own
    # transaction via its extra_writes hook).
    ("POST", "/admin/firms"): MUTATION_KIND_FIRESTORE,
    ("PATCH", "/admin/firms/{firm_id}/status"): MUTATION_KIND_FIRESTORE,
    ("PATCH", "/admin/firms/{firm_id}/allowed_kits"): MUTATION_KIND_FIRESTORE,
    ("PATCH", "/admin/firms/{firm_id}/kind"): MUTATION_KIND_FIRESTORE,
    ("POST", "/admin/firms/{firm_id}/credits/grant"): MUTATION_KIND_FIRESTORE,
    ("POST", "/admin/firms/{firm_id}/credits/adjust"): MUTATION_KIND_FIRESTORE,
    # The sweep route joins bead A5's refund_expired_link transaction in
    # backend/services/credit_ledger.py via that function's extra_writes
    # seam (bd polyglot-pdf-8vgfh) -- the identical delegated-write shape
    # credit_routes.py uses with append_entry, so it is FIRESTORE too; see
    # _EXTRA_WRITES_TRANSACTION_OPENERS below.
    ("POST", "/admin/links/sweep-expired"): MUTATION_KIND_FIRESTORE,
    # Link revoke (bd polyglot-pdf-jmiys, Track B bead B4). Opens its OWN
    # transaction (mirrors firm_routes.py's _apply_firm_patch shape) --
    # there is no balance mutation to join via extra_writes, since revoke
    # touches only links[_<channel>]/{jti}.status.
    ("POST", "/admin/links/{jti}/revoke"): MUTATION_KIND_FIRESTORE,
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


# Calls that OPEN a caller's own transaction ON THE CALLER'S BEHALF via a
# documented `extra_writes(tx, firm)` extension point, rather than the
# caller decorating its own function with @firestore.transactional. Both
# are `backend/services/credit_ledger.py` helpers: append_entry() runs
# extra_writes INSIDE its own transaction body, after its reads and
# alongside its balance/entry writes (module docstring: "It is a callable
# taking (tx, firm_snapshot_dict)... runs INSIDE the body, AFTER the
# reads"), and refund_expired_link() uses the same hook internally. A
# route that joins its audit row to ONE of these calls via extra_writes
# gets the identical in-transaction guarantee a route that opens its own
# transaction gets -- credit_ledger.py's own tests
# (test_the_refund_and_the_status_flip_commit_ATOMICALLY,
# test_a_forced_audit_failure_leaves_the_config_unchanged's sibling in
# test_credit_routes.py) pin that the hook really does run inside the
# commit, not alongside it. Named here (not derived from credit_ledger.py
# itself) because this is a STATIC check over the ROUTE module's own
# source; it does not need to re-derive credit_ledger's internals, only to
# recognize the one extension point its public API documents.
_EXTRA_WRITES_TRANSACTION_OPENERS = frozenset({
    "append_entry", "refund_expired_link",
})


def _extra_writes_callback_names(tree) -> set:
    """The name of the function object passed as `extra_writes=...` to a
    call to one of _EXTRA_WRITES_TRANSACTION_OPENERS, anywhere in the
    module -- so its body can be looked up and treated as transactional
    below. Handles the plain `def _audit(tx, firm): ...` shape (a Name
    reference to a function defined elsewhere in the same module); a
    lambda or an inline call expression passed directly is out of scope
    here because neither shape appears in this repo's routes today, and a
    route that used one would still fail the OTHER half of this check (the
    call inside it would not resolve to a named FunctionDef this walk can
    find), which is a legitimate red rather than a blind spot.
    """
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called_name = None
        if isinstance(func, ast.Attribute):
            called_name = func.attr
        elif isinstance(func, ast.Name):
            called_name = func.id
        if called_name not in _EXTRA_WRITES_TRANSACTION_OPENERS:
            continue
        for kw in node.keywords:
            if kw.arg == "extra_writes" and isinstance(kw.value, ast.Name):
                names.add(kw.value.id)
    return names


def _calls_inside_transactional_bodies(tree) -> set:
    """Every name called inside SOME @firestore.transactional function, OR
    inside a function passed as `extra_writes=` to append_entry /
    refund_expired_link (see _EXTRA_WRITES_TRANSACTION_OPENERS above).

    This is the check that gives the Firestore form its teeth: a module can
    call record_in_transaction from anywhere, but only a call inside a
    transactional body -- OWN or borrowed via the documented extension
    point -- is actually in the mutation's transaction.
    """
    extra_writes_names = _extra_writes_callback_names(tree)
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_transactional(node) or node.name in extra_writes_names:
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

    Mutation (Firestore routes, own transaction): delete the
    record_in_transaction call from config_routes._apply_config_write --
    red. Move that call OUT of the @firestore.transactional body into the
    enclosing function -- ALSO red, which is the half a presence check
    would miss.

    Mutation (Firestore routes, extra_writes-delegated, e.g. credit_
    routes.py or the sweep route): rename the audit closure without
    updating the extra_writes= call site -- red (the closure is no longer
    found by name). Stop passing it as extra_writes= at all -- red.

    Mutation (external routes): delete record_pending -- red; delete both
    mark_committed and mark_failed -- red.
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
        # the real write sat outside. A route using the extra_writes
        # extension point (see _EXTRA_WRITES_TRANSACTION_OPENERS) never
        # calls tx.set itself -- append_entry / refund_expired_link do that
        # internally -- so the module-level call to one of THOSE names is
        # the mutation-write evidence for that shape instead.
        writes_own_doc = "set" in in_tx or "update" in in_tx or "delete" in in_tx
        delegates_the_write = bool(
            module_calls & _EXTRA_WRITES_TRANSACTION_OPENERS)
        assert writes_own_doc or delegates_the_write, (
            "{} {}'s @firestore.transactional body writes nothing, and the "
            "module calls none of {} either -- the audit row is inside a "
            "transaction the mutation is not in".format(
                method, path, sorted(_EXTRA_WRITES_TRANSACTION_OPENERS)))
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

# The EXTRA_WRITES shape (bd polyglot-pdf-zopqq's credit_routes.py): the
# route never opens its own transaction or calls tx.set -- it joins its
# audit row to credit_ledger.append_entry's OWN transaction via the
# documented extra_writes(tx, firm) hook.
_FIRESTORE_ROUTE_EXTRA_WRITES_OK = """
from admin_backend.services import audit_log
from backend.services import credit_ledger

def handler():
    def _audit(tx, firm):
        audit_log.record_in_transaction(tx, db)
    credit_ledger.append_entry(db, extra_writes=_audit)
"""

# The regression this bead's extension must still catch: an audit call
# that exists in the module but OUTSIDE the extra_writes callback -- e.g.
# fired after append_entry returns, the exact double-apply window the
# in-transaction form exists to close. Presence-only detection (checking
# only that append_entry and record_in_transaction are both called
# somewhere) would wave this through; the callback-body check must not.
_FIRESTORE_ROUTE_EXTRA_WRITES_AUDIT_OUTSIDE_CALLBACK = """
from admin_backend.services import audit_log
from backend.services import credit_ledger

def handler():
    def _audit(tx, firm):
        pass
    credit_ledger.append_entry(db, extra_writes=_audit)
    audit_log.record_in_transaction(None, db)
"""


def _firestore_verdict(source: str) -> bool:
    """The SAME two checks the Firestore branch above applies (including
    the extra_writes extension for a route that delegates its write to
    append_entry / refund_expired_link -- see
    _EXTRA_WRITES_TRANSACTION_OPENERS)."""
    tree = ast.parse(source)
    module_calls = _called_names(tree)
    if "record_in_transaction" not in module_calls:
        return False
    in_tx = _calls_inside_transactional_bodies(tree)
    if "record_in_transaction" not in in_tx:
        return False
    writes_own_doc = bool({"set", "update", "delete"} & in_tx)
    delegates_the_write = bool(module_calls & _EXTRA_WRITES_TRANSACTION_OPENERS)
    return writes_own_doc or delegates_the_write


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
    (_FIRESTORE_ROUTE_EXTRA_WRITES_OK, True,
     "the correct extra_writes-delegated form (bd polyglot-pdf-zopqq)"),
    (_FIRESTORE_ROUTE_EXTRA_WRITES_AUDIT_OUTSIDE_CALLBACK, False,
     "delegates the write via extra_writes, but audits OUTSIDE the callback"),
], ids=["correct-form", "no-audit-call", "audits-outside-the-transaction",
        "extra-writes-correct-form", "extra-writes-audit-outside-callback"])
def test_the_firestore_check_goes_red_on_a_dropped_in_transaction_call(
        source, expected, why):
    """EXIT CRITERION 2, direction one. Runs the real derivation against
    hand-built route shapes: a Firestore route that drops the in-transaction
    call, and -- the case a presence check would wave through -- one that
    audits outside the transaction. The two extra-writes cases are the same
    proof for the DELEGATED-write shape credit_routes.py uses (bd
    polyglot-pdf-zopqq): a route that never calls tx.set itself, and whose
    only mutation evidence is a call to append_entry/refund_expired_link,
    must still fail when its audit call sits outside the extra_writes
    callback that actually runs inside that helper's transaction."""
    assert _firestore_verdict(source) is expected, why


@pytest.mark.parametrize("source,expected,why", [
    (_EXTERNAL_ROUTE_OK, True, "the correct pending-then-committed form"),
    (_EXTERNAL_ROUTE_NO_PENDING, False, "no pending row at all"),
    (_EXTERNAL_ROUTE_NEVER_CLOSED, False,
     "a pending row nothing ever closes out"),
], ids=["correct-form", "no-pending-row", "pending-row-never-closed"])
def test_the_external_check_goes_red_on_a_skipped_pending_row(
        source, expected, why):
    """EXIT CRITERION 2, direction two. The synthetic shapes stay even now
    that the external form HAS consuming routes (the three user routes, bd
    polyglot-pdf-dmjl5): the real routes prove the form is USED, these prove
    the CHECK still goes red when it is skipped -- which no live route can
    demonstrate without being broken on purpose."""
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


def test_the_shipped_user_routes_pass_the_synthetic_external_check():
    """The external counterpart of the tie-back above (bd polyglot-pdf-dmjl5).

    Without it the external branch would be graded only against toy sources
    while the live derivation ran different code -- the exact asymmetry the
    Firestore tie-back exists to close. Same function, real file."""
    from admin_backend.routes import user_routes

    source = pathlib.Path(
        inspect.getsourcefile(user_routes)).read_text(encoding="utf-8")
    assert _external_verdict(source), (
        "user_routes.py does not satisfy the same pending-then-committed "
        "check the synthetic cases are graded against")


def test_the_shipped_firm_routes_pass_the_synthetic_firestore_check():
    """The firm_routes.py counterpart of the config tie-back (bd
    polyglot-pdf-zopqq): firm_routes.py opens its OWN transactions (like
    config_routes.py), so it is graded against the plain in-transaction
    form, not the extra_writes extension."""
    from admin_backend.routes import firm_routes

    source = pathlib.Path(
        inspect.getsourcefile(firm_routes)).read_text(encoding="utf-8")
    assert _firestore_verdict(source), (
        "firm_routes.py does not satisfy the same in-transaction check the "
        "synthetic cases are graded against")


def test_the_shipped_credit_routes_pass_the_synthetic_extra_writes_check():
    """The extra_writes counterpart of the tie-back above (bd
    polyglot-pdf-zopqq): credit_routes.py never opens its own transaction --
    it joins credit_ledger.append_entry's via extra_writes -- so this ties
    THAT shape, specifically, to the real file rather than only to the
    synthetic _FIRESTORE_ROUTE_EXTRA_WRITES_OK source above."""
    from admin_backend.routes import credit_routes

    source = pathlib.Path(
        inspect.getsourcefile(credit_routes)).read_text(encoding="utf-8")
    assert _firestore_verdict(source), (
        "credit_routes.py does not satisfy the same extra_writes-delegated "
        "in-transaction check the synthetic cases are graded against")


def test_the_shipped_sweep_routes_pass_the_synthetic_extra_writes_check():
    """The sweep_routes.py counterpart of the tie-back above (bd
    polyglot-pdf-8vgfh): sweep_routes.py never opens its own transaction
    either -- it joins credit_ledger.refund_expired_link's via extra_writes,
    the OTHER name in _EXTRA_WRITES_TRANSACTION_OPENERS -- so this ties
    THAT shape, specifically, to the real file rather than only to the
    synthetic _FIRESTORE_ROUTE_EXTRA_WRITES_OK source above (which exercises
    append_entry)."""
    from admin_backend.routes import sweep_routes

    source = pathlib.Path(
        inspect.getsourcefile(sweep_routes)).read_text(encoding="utf-8")
    assert _firestore_verdict(source), (
        "sweep_routes.py does not satisfy the same extra_writes-delegated "
        "in-transaction check the synthetic cases are graded against")


def test_the_shipped_link_routes_pass_the_synthetic_firestore_check():
    """The link_routes.py counterpart of the config tie-back (bd
    polyglot-pdf-jmiys): revoke_link opens its OWN transaction (like
    firm_routes.py), so it is graded against the plain in-transaction form,
    not the extra_writes extension -- there is no balance mutation for it
    to join."""
    from admin_backend.routes import link_routes

    source = pathlib.Path(
        inspect.getsourcefile(link_routes)).read_text(encoding="utf-8")
    assert _firestore_verdict(source), (
        "link_routes.py does not satisfy the same in-transaction check the "
        "synthetic cases are graded against")
