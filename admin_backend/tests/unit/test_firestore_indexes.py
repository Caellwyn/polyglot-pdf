"""Every composite-index-requiring query ships the index it needs.

WHY THIS FILE EXISTS (CLAUDE.md scar #7, applied to INDEXES not IAM). A mock
cannot tell you the real datastore will refuse a query. test_audit_log.py
substitutes an in-memory _Query that filters and sorts in Python, so every
GET /admin/audit test passes whether or not Firestore would serve the query.
Firestore serves an EQUALITY filter combined with an order_by on a DIFFERENT
field only from a COMPOSITE INDEX; without one the query fails at runtime
with FAILED_PRECONDITION. Before bd polyglot-pdf-li9x0 this repo shipped no
firestore.indexes.json at all, and backend/utils/confirmation_logger.py
deliberately avoids order_by for exactly that reason.

WHY IT IS SET-DERIVED AND NOT FOUR HAND-WRITTEN ASSERTIONS (CLAUDE.md scar
#8, enumerate the set). The filter list is read out of the ROUTE SOURCE by
AST, not typed here. Adding a fifth filter to GET /admin/audit without
adding its index to firestore.indexes.json fails HERE, at the moment the
filter is added -- rather than in production the first time an operator uses
it. Hand-listing the four fields would pin the instance and miss the fifth.

ALSO COVERS reconcile_expired_for_firm's links[_<channel>] QUERY (bd
polyglot-pdf-1op3g cross-surface review finding 1, added after the audit-log
guard above already existed). That query adds a RANGE filter
(open_deadline <) on top of two equality filters -- a shape the all-equality
audit-log queries above never hit, and one Firestore's automatic
single-field index merging does NOT cover. The guard below is the same
AST-read-the-real-query-and-check-the-shipped-index pattern, extended to a
second collection family.

ALSO COVERS sweep_routes._sweep_channel's links[_<channel>] QUERY (bd
polyglot-pdf-8vgfh cross-surface review finding 1). This is a SECOND,
DIFFERENT query against the SAME two collections: `status == minted AND
open_deadline < now`, with NO firm_id filter (the sweep is deliberately
cross-firm -- see sweep_routes.py's own module docstring). Firestore serves
a composite query only from an index whose fields are a PREFIX match of the
query's constrained fields; the (firm_id, status, open_deadline) index above
cannot serve a query that constrains no firm_id at all, so this needs its
OWN (status, open_deadline) index per collection. Because two DIFFERENT
queries now share a collectionGroup, the guard below identifies each
shipped index by its FIELD-NAME SET, not merely by collectionGroup --
`len(matches) == 1` per collectionGroup would break the moment a second,
legitimately-different query joined the same collection.

ASCII only.
"""
import ast
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
INDEXES_FILE = REPO_ROOT / "firestore.indexes.json"
FIREBASE_JSON = REPO_ROOT / "firebase.json"
AUDIT_ROUTES = REPO_ROOT / "admin_backend" / "routes" / "audit_routes.py"
CREDIT_LEDGER = REPO_ROOT / "backend" / "services" / "credit_ledger.py"
SWEEP_ROUTES = REPO_ROOT / "admin_backend" / "routes" / "sweep_routes.py"

# The collection GET /admin/audit queries. Kept as a literal (not imported)
# so a rename of audit_log.COLLECTION that forgets the index artifact is
# caught here rather than silently re-pointing the assertion at the new name.
AUDIT_COLLECTION = "admin_audit_log"

# The order_by pair the route applies after its filters. Same rationale.
EXPECTED_ORDER = (("ts", "DESCENDING"), ("__name__", "DESCENDING"))

# The two collectionGroups reconcile_expired_for_firm's query can hit -- one
# per channel that exists in production (link_tokens.DEFAULT_CHANNEL="demo"
# keeps the bare name; every other channel, only "staging" today, suffixes
# it). Kept as literals rather than imported so a rename of links_store's
# naming scheme is caught here, not silently re-pointed.
LINKS_COLLECTIONS = ("links", "links_staging")


def _route_filter_fields():
    """The equality-filter field names GET /admin/audit actually builds.

    Read from the route's AST rather than typed here: the route builds its
    filters by iterating a tuple of (field_name, value) pairs, so the field
    names are the string literals in that tuple. This is what makes the test
    track the route instead of a copy of it.
    """
    tree = ast.parse(AUDIT_ROUTES.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # for <targets> in ( ("action", action), ... ):
        if not isinstance(node, ast.For):
            continue
        if not isinstance(node.iter, (ast.Tuple, ast.List)):
            continue
        fields = []
        for element in node.iter.elts:
            if not isinstance(element, ast.Tuple) or not element.elts:
                fields = []
                break
            first = element.elts[0]
            if not isinstance(first, ast.Constant) or not isinstance(
                    first.value, str):
                fields = []
                break
            fields.append(first.value)
        if fields:
            return tuple(fields)
    raise AssertionError(
        "could not find the filter-field tuple in {} -- if the route stopped "
        "building its filters from a literal tuple, this extractor needs "
        "updating, NOT deleting: the index guard depends on it".format(
            AUDIT_ROUTES.name))


def _shipped_indexes():
    data = json.loads(INDEXES_FILE.read_text(encoding="utf-8"))
    return data.get("indexes", [])


def _query_filters_in_function(path, function_name):
    """The (field, operator) pairs a named function's Firestore query
    actually chains, IN ORDER, read from `path`'s AST rather than typed
    here (same rationale as _route_filter_fields() above: the guard must
    track the query, not a copy of it).

    Shared by reconcile_expired_for_firm (credit_ledger.py) and
    _sweep_channel (sweep_routes.py) -- both build their query as a chain
    of `.where(filter=FieldFilter(<field>, <op>, <value>))` calls inside a
    `try:` branch (the `google.cloud.firestore_v1.base_query.FieldFilter`
    import succeeds on every SDK version this repo runs; the `except
    ImportError:` branch in each is a positional-args fallback for an older
    SDK and repeats the SAME field/operator pairs, so reading either branch
    gives the same answer -- this reads the try branch).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name == function_name):
            continue
        pairs = []
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            if not (isinstance(call.func, ast.Attribute)
                    and call.func.attr == "where"):
                continue
            # .where(filter=FieldFilter(field, op, value))
            for kw in call.keywords:
                if kw.arg != "filter":
                    continue
                inner = kw.value
                if not (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == "FieldFilter"
                        and len(inner.args) >= 2):
                    continue
                field_arg, op_arg = inner.args[0], inner.args[1]
                if not (isinstance(field_arg, ast.Constant)
                        and isinstance(op_arg, ast.Constant)):
                    continue
                pairs.append((field_arg.value, op_arg.value))
        if pairs:
            return tuple(pairs)
    raise AssertionError(
        "could not find a FieldFilter .where() chain in {}() ({}) -- if the "
        "query stopped building its filters via FieldFilter, this extractor "
        "needs updating, NOT deleting: the links index guard depends on "
        "it".format(function_name, path.name))


def _reconcile_query_filters():
    return _query_filters_in_function(CREDIT_LEDGER,
                                       "reconcile_expired_for_firm")


def _sweep_query_filters():
    return _query_filters_in_function(SWEEP_ROUTES, "_sweep_channel")


def _index_field_names(index):
    return tuple(f["fieldPath"] for f in index.get("fields", []))


def _matching_indexes(collection, field_names):
    """Shipped indexes for `collection` whose field-NAME SET (order-
    independent) matches `field_names` exactly. Used to pick out ONE of
    several legitimately-different queries sharing a collectionGroup, so a
    second query joining the collection doesn't make `len(matches) == 1`
    collectionGroup-only assertions ambiguous.
    """
    wanted = set(field_names)
    return [
        index for index in _shipped_indexes()
        if index.get("collectionGroup") == collection
        and set(_index_field_names(index)) == wanted
    ]


def test_indexes_file_is_wired_into_firebase_json():
    """An index artifact nothing deploys is not an index."""
    firebase = json.loads(FIREBASE_JSON.read_text(encoding="utf-8"))
    assert firebase.get("firestore", {}).get("indexes") == \
        "firestore.indexes.json"


def test_the_firestore_rules_target_ships_the_indexes_too():
    """firestore:indexes is deployed, by the same target as the rules.

    Rules and indexes are both PROJECT-wide, so they belong to the same
    target and the same channel: `firestore-rules`, which only deploy-demo.sh
    runs. A deploy-staging.sh that ran it would push project-wide state from
    the disposable channel.

    Read from cloudbuild.yaml because that is where the deploy lives (bd
    polyglot-pdf-oqtm7). deploy-demo.sh shipped BOTH inline until it became a
    thin trigger wrapper; the target carried only the rules at that moment, so
    the indexes moved into it rather than being silently retired -- which is
    the failure this test exists to catch, and did.
    """
    build = (REPO_ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")
    assert "firebase-tools deploy --only firestore:rules" in build
    assert "firebase-tools deploy --only firestore:indexes" in build, (
        "the firestore-rules target ships the rules but not the composite "
        "indexes -- a query combining an equality filter with an order_by on "
        "a different field then fails at runtime with FAILED_PRECONDITION"
    )
    # CODE lines only, and the QUOTED target token. Both wrappers explain the
    # target in prose, so a plain substring search over the whole file matches
    # the comment and passes even when the target is not run at all
    # (mutation-verified: deleting it from deploy-demo.sh's TARGETS list left
    # this green until these two lines were narrowed).
    def _targets(name):
        body = (REPO_ROOT / name).read_text(encoding="utf-8")
        return "\n".join(
            ln for ln in body.splitlines() if not ln.lstrip().startswith("#")
        )

    assert '"firestore-rules"' in _targets("deploy-demo.sh"), (
        "deploy-demo.sh no longer runs the firestore-rules target, so nothing "
        "ships rules or indexes"
    )
    assert '"firestore-rules"' not in _targets("deploy-staging.sh")


def test_every_audit_filter_has_a_composite_index():
    """THE SET GUARD. One index per filter the route can apply.

    Each filtered query is `where(<field> == v).order_by(ts DESC)
    .order_by(__name__ DESC)`, which Firestore serves only from a composite
    index whose fields are exactly (<field> ASC, ts DESC, __name__ DESC).
    """
    shipped = _shipped_indexes()
    by_first_field = {}
    for index in shipped:
        if index.get("collectionGroup") != AUDIT_COLLECTION:
            continue
        fields = index.get("fields", [])
        assert fields, "index with no fields: {}".format(index)
        by_first_field[fields[0]["fieldPath"]] = fields

    missing = [f for f in _route_filter_fields() if f not in by_first_field]
    assert not missing, (
        "GET /admin/audit filters on {} but firestore.indexes.json ships no "
        "composite index for them. Every such query will fail in production "
        "with FAILED_PRECONDITION while the local suite stays green (the "
        "test fake sorts in Python). Add the index, do not delete this "
        "assertion.".format(missing))


@pytest.mark.parametrize("field", _route_filter_fields())
def test_each_audit_index_has_the_exact_query_shape(field):
    """Shape, not just presence.

    A composite index only serves a query whose field order and directions
    match it exactly. An index of (action ASC, ts ASC) does not serve an
    order_by(ts DESCENDING) query, so asserting presence alone would pass a
    useless index.
    """
    matches = [
        index for index in _shipped_indexes()
        if index.get("collectionGroup") == AUDIT_COLLECTION
        and index.get("fields", [{}])[0].get("fieldPath") == field
    ]
    assert len(matches) == 1, (
        "expected exactly one {} index keyed on {}, found {}".format(
            AUDIT_COLLECTION, field, len(matches)))
    fields = matches[0]["fields"]
    assert matches[0].get("queryScope") == "COLLECTION"
    assert (fields[0]["fieldPath"], fields[0]["order"]) == (field, "ASCENDING")
    tail = tuple((f["fieldPath"], f["order"]) for f in fields[1:])
    assert tail == EXPECTED_ORDER, (
        "index for {} orders by {}, but the route orders by {}".format(
            field, tail, EXPECTED_ORDER))


def test_no_unused_audit_indexes():
    """The set is CLOSED in both directions.

    An index nothing queries is a silent write-amplification cost on every
    audit row. If a filter is removed from the route, its index must go too.
    """
    filters = set(_route_filter_fields())
    shipped_fields = {
        index["fields"][0]["fieldPath"]
        for index in _shipped_indexes()
        if index.get("collectionGroup") == AUDIT_COLLECTION
    }
    assert shipped_fields == filters, (
        "index set {} does not match the route's filter set {}".format(
            sorted(shipped_fields), sorted(filters)))


# ---------------------------------------------------------------------
# reconcile_expired_for_firm's links[_<channel>] query (bd polyglot-pdf-1op3g
# cross-surface review finding 1). Unlike the all-equality audit-log
# queries above, this one adds a RANGE filter (open_deadline < deadline) on
# top of two equality filters (firm_id ==, status ==) -- Firestore's
# automatic single-field index merging covers all-equality queries only, so
# this shape needs a composite index that firestore.indexes.json did not
# ship until this bead. Both channels that exist in production (the bare
# "links" collection for the demo channel, "links_staging" for staging) need
# their own index: collectionGroup scoping in firestore.indexes.json is
# per-name, not per-query-shape, and the two collections are otherwise
# identical in structure (links_store.py's doc shape is the same for both).
# ---------------------------------------------------------------------


def test_reconcile_query_needs_a_range_filter_the_audit_queries_do_not():
    """Sanity-check on the extractor itself: if this ever reads as all
    equality, the "composite index required" premise below is gone and the
    whole block needs re-deriving, not just re-running."""
    ops = [op for _field, op in _reconcile_query_filters()]
    assert "<" in ops, (
        "reconcile_expired_for_firm's query no longer has a range filter -- "
        "if it is now all-equality, Firestore's automatic single-field "
        "index merging may cover it and this index-guard block should be "
        "re-evaluated, not silently kept")


def _assert_composite_index_for_query(collection, filters, *, query_label,
                                       reason_extra=""):
    """Shared shape assertion: exactly one shipped index, on `collection`,
    whose field-NAME SET matches `filters` exactly, with the equality
    fields (in any order) ahead of the single range field and every field
    ASCENDING (neither query being guarded here has an order_by).

    Factored out of the old per-query test bodies so reconcile_expired_
    for_firm's and _sweep_channel's queries -- two DIFFERENT filter shapes
    that now share the same two collections -- get byte-identical shape
    checking instead of one being a copy that could drift from the other.
    """
    equality_fields = [f for f, op in filters if op != "<"]
    range_fields = [f for f, op in filters if op == "<"]
    assert len(range_fields) == 1, (
        "expected exactly one range filter in {}'s query, found {}".format(
            query_label, range_fields))

    field_names = equality_fields + range_fields
    matches = _matching_indexes(collection, field_names)
    assert len(matches) == 1, (
        "expected exactly one composite index for the {} collection "
        "matching {}'s field set {}, found {}. Without it the query fails "
        "in production with FAILED_PRECONDITION while every local test "
        "stays green (the test fake filters in Python).{}".format(
            collection, query_label, sorted(field_names), len(matches),
            reason_extra))

    fields = matches[0].get("fields", [])
    assert matches[0].get("queryScope") == "COLLECTION"
    assert len(fields) == len(filters), (
        "index for {} ({}) has {} fields but the query filters on {}".format(
            collection, query_label, len(fields), len(filters)))
    shipped_field_names = [f["fieldPath"] for f in fields]
    assert set(shipped_field_names[:-1]) == set(equality_fields), (
        "index for {} ({}) does not lead with the query's equality fields "
        "{}: got {}".format(collection, query_label, equality_fields,
                             shipped_field_names))
    assert shipped_field_names[-1] == range_fields[0], (
        "index for {} ({}) must end with the range field {} (Firestore "
        "composite indexes require the range field last): got {}".format(
            collection, query_label, range_fields[0], shipped_field_names))
    assert all(f["order"] == "ASCENDING" for f in fields), (
        "index for {} ({}) has a non-ASCENDING field; the query has no "
        "order_by, so every field must be ASCENDING: {}".format(
            collection, query_label, fields))


@pytest.mark.parametrize("collection", LINKS_COLLECTIONS)
def test_reconcile_query_has_a_composite_index(collection):
    """THE SET GUARD for reconcile_expired_for_firm's links query, mirroring
    test_every_audit_filter_has_a_composite_index above. See
    _assert_composite_index_for_query's docstring for the shape rationale;
    see backend/utils/confirmation_logger.py:995-1004 for why the
    ALL-EQUALITY sibling query needs no index and this one, which adds a
    range filter, does.
    """
    _assert_composite_index_for_query(
        collection, _reconcile_query_filters(),
        query_label="reconcile_expired_for_firm")


@pytest.mark.parametrize("collection", LINKS_COLLECTIONS)
def test_sweep_query_has_a_composite_index(collection):
    """THE SET GUARD for _sweep_channel's links query (bd
    polyglot-pdf-8vgfh cross-surface review finding 1).

    This is a DIFFERENT query than reconcile_expired_for_firm's on the SAME
    collection -- `status == minted AND open_deadline < now`, with no
    firm_id filter (the sweep is deliberately cross-firm). The
    (firm_id, status, open_deadline) index that serves reconcile's query
    cannot serve this one: Firestore only serves a query from an index
    whose fields are a PREFIX match of the query's constrained fields, and
    this query constrains no firm_id at all. It needs its OWN
    (status, open_deadline) index per collection.
    """
    _assert_composite_index_for_query(
        collection, _sweep_query_filters(),
        query_label="_sweep_channel",
        reason_extra=" See sweep_routes.py's module docstring for why this "
                      "query has no firm_id filter and therefore cannot "
                      "reuse reconcile_expired_for_firm's index.")


def test_reconcile_and_sweep_queries_are_a_different_shape():
    """Sanity-check on the two extractors together: if the two queries ever
    end up with the SAME field set, the two-index-per-collection premise
    above is gone (one index would serve both) and this whole block should
    be re-derived, not silently kept with a redundant second index."""
    reconcile_fields = {f for f, _op in _reconcile_query_filters()}
    sweep_fields = {f for f, _op in _sweep_query_filters()}
    assert reconcile_fields != sweep_fields, (
        "reconcile_expired_for_firm's query fields {} now match "
        "_sweep_channel's {} -- one composite index would serve both; "
        "drop the redundant one rather than leaving two".format(
            sorted(reconcile_fields), sorted(sweep_fields)))


def test_no_unused_links_indexes():
    """The set is CLOSED in both directions, same as the audit-log guard.

    An index on a links collectionGroup nothing queries (a stale channel
    name, a leftover from a renamed collection, a field-shape no query
    matches) is a silent write-amplification cost on every mint/refund
    write to that collection. Checks the FULL (collection, field-set) pair,
    not just the collectionGroup name, since two live queries now share
    each links collectionGroup with different field shapes.
    """
    reconcile_fields = tuple(f for f, _op in _reconcile_query_filters())
    sweep_fields = tuple(f for f, _op in _sweep_query_filters())
    expected = set()
    for collection in LINKS_COLLECTIONS:
        expected.add((collection, frozenset(reconcile_fields)))
        expected.add((collection, frozenset(sweep_fields)))

    shipped = set()
    for index in _shipped_indexes():
        collection = index.get("collectionGroup")
        if collection not in LINKS_COLLECTIONS:
            continue
        shipped.add((collection, frozenset(_index_field_names(index))))

    assert shipped == expected, (
        "shipped links indexes {} do not match the expected "
        "(collection, field-set) pairs {} -- add or remove an index, do "
        "not let them diverge".format(
            sorted(shipped, key=str), sorted(expected, key=str)))
