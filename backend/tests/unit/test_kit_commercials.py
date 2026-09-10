"""backend/services/kit_commercials.py's resolve_commercial (bd
polyglot-pdf-zcbm1: resolve_commercial never returned `display`, so the
admin console's GET routes -- both of which spread this reader's return
dict -- could never surface a kit's stored console label, and a console
PUT (which replaces the whole commercial doc) silently wiped it on every
price edit).

Pins the NEW `display` key: passed through verbatim when the stored doc has
one, `{}` for a missing doc, a missing key, or a malformed value (a
non-dict, or a dict with a non-string key/value) -- unlike credit_cost/
cap_usd, `display` has no global default to fall back to, so `{}` IS its
default rather than a fallback FROM something.

Each test's docstring names the mutation that must turn it red.

ASCII only.
"""
from __future__ import annotations

import pytest

from backend.services import kit_commercials


class _FakeSnap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, data):
        self._data = data

    def get(self):
        return _FakeSnap(self._data)


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def document(self, doc_id):
        return _FakeDocRef(self._docs.get(doc_id))


class _FakeDb:
    def __init__(self, docs):
        self._docs = docs

    def collection(self, name):
        assert name == kit_commercials.COLLECTION
        return _FakeCollection(self._docs)


@pytest.fixture
def fake_db(monkeypatch):
    """Installs a fake Firestore client returning `docs` (a {kit_id: dict}
    map) for backend.services.auth.get_db -- the lazy import
    kit_commercials.read_commercial uses."""
    docs: dict[str, dict] = {}

    def _install(new_docs):
        docs.clear()
        docs.update(new_docs)
        return docs

    db = _FakeDb(docs)
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return _install


def test_resolve_commercial_passes_through_a_stored_display_map(fake_db):
    """THE FIX. Mutation: revert resolve_commercial to not include
    "display" in its return dict (or to hardcode {}) -- this goes red on
    the equality assertion."""
    fake_db({"w-7": {
        "credit_cost": 2, "burn_cap_usd": 5.0,
        "display": {"label": "Form W-7"},
    }})
    resolved = kit_commercials.resolve_commercial("w-7")
    assert resolved["display"] == {"label": "Form W-7"}


def test_resolve_commercial_defaults_display_to_empty_map_when_absent_from_doc(
        fake_db):
    """A real commercial doc that simply never had a display key (e.g.
    written before this bead, or by a caller that omitted it) -- resolve
    to {}, not None or a KeyError.

    Mutation: `doc.get("display")` with no default -- this goes red with a
    KeyError-shaped failure (None != {})."""
    fake_db({"w-7": {"credit_cost": 2, "burn_cap_usd": 5.0}})
    resolved = kit_commercials.resolve_commercial("w-7")
    assert resolved["display"] == {}


def test_resolve_commercial_defaults_display_to_empty_map_when_no_doc_at_all(
        fake_db):
    """No commercial doc at all (kit never priced) -- source is "default"
    and display is still a usable {}, not None."""
    fake_db({})
    resolved = kit_commercials.resolve_commercial("never-priced")
    assert resolved["source"] == "default"
    assert resolved["display"] == {}


@pytest.mark.parametrize("bad_display", [
    "not-a-dict", ["a", "list"], 5, True,
    {"label": 5},
    {5: "label"},
])
def test_resolve_commercial_defaults_display_to_empty_map_on_a_malformed_value(
        fake_db, bad_display):
    """A malformed stored display (wrong type entirely, or a dict with a
    non-string key/value) degrades to {} rather than being handed to the
    caller raw -- the same defensive-parsing posture credit_cost/
    burn_cap_usd already apply to their own malformed values.

    Mutation: `doc.get("display", {})` with no shape validation -- this
    goes red by returning the malformed value verbatim instead of {}."""
    fake_db({"w-7": {
        "credit_cost": 2, "burn_cap_usd": 5.0, "display": bad_display,
    }})
    resolved = kit_commercials.resolve_commercial("w-7")
    assert resolved["display"] == {}


def test_resolve_commercial_display_never_affects_credit_cost_or_cap_usd(
        fake_db):
    """A malformed display must not knock over the OTHER two numbers --
    they resolve independently. Mutation: an early return / exception on
    bad display before credit_cost/cap_usd are computed -- this goes red
    (wrong numbers, or an unhandled exception)."""
    fake_db({"w-7": {
        "credit_cost": 3, "burn_cap_usd": 7.5, "display": "garbage",
    }})
    resolved = kit_commercials.resolve_commercial("w-7")
    assert resolved["credit_cost"] == 3
    assert resolved["cap_usd"] == 7.5
    assert resolved["source"] == "kit"
    assert resolved["display"] == {}
