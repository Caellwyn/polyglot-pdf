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

# The collection GET /admin/audit queries. Kept as a literal (not imported)
# so a rename of audit_log.COLLECTION that forgets the index artifact is
# caught here rather than silently re-pointing the assertion at the new name.
AUDIT_COLLECTION = "admin_audit_log"

# The order_by pair the route applies after its filters. Same rationale.
EXPECTED_ORDER = (("ts", "DESCENDING"), ("__name__", "DESCENDING"))


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


def test_indexes_file_is_wired_into_firebase_json():
    """An index artifact nothing deploys is not an index."""
    firebase = json.loads(FIREBASE_JSON.read_text(encoding="utf-8"))
    assert firebase.get("firestore", {}).get("indexes") == \
        "firestore.indexes.json"


def test_deploy_demo_ships_the_indexes():
    """firestore:indexes is deployed, and by the same script as the rules.

    Rules and indexes are both PROJECT-wide, so they belong to the same
    channel: deploy-demo.sh. A deploy-staging.sh that shipped them would
    push project-wide state from the disposable channel.
    """
    demo = (REPO_ROOT / "deploy-demo.sh").read_text(encoding="utf-8")
    assert "firebase deploy --only firestore:indexes" in demo
    staging = (REPO_ROOT / "deploy-staging.sh").read_text(encoding="utf-8")
    assert "firestore:indexes" not in staging


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
