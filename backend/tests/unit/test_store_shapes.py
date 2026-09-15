"""Store-shape allowlists for the data-at-rest inventory (bd polyglot-pdf-uaxt5,
sprint 23 workstream A, PF-8's retention half + PF-9).

WHY THIS FILE, ON TOP OF THE EXISTING PER-STORE PINS. Several stores already
carry an exact-key allowlist test at their own module's test file:
confirmation_events (test_confirmation_firestore_sink.py), the credit ledger
entry (test_credit_ledger.py's ENTRY_FIELDS check), the usage-event envelope
(test_usage_event_schema.py), admin_audit_log rows and the firms/{firm_id}
doc (admin_backend/tests/unit/test_audit_log_shapes.py, this same bead).
`links[_<channel>]` mint records and `link_redemptions[_<channel>]` records
had NO such pin before this bead -- links_store.build_mint_record() and
link_redemptions.open_link() are each the ONE place their document shape is
defined, but nothing asserted the exact key set stayed closed. Both stores
are named explicitly in the sprint-23 plan's retention-policy ask (link
expiry / TTL) and in scripts/audit/inventory_stores.py's pinned allowlist
map, so this file is where the code-side half of that inventory row lives.

Pins are exact-key-set (`==`), never a subset check -- a future field added
to either builder must be a deliberate, reviewed addition to the allowlist
here, not a silent pass.

ASCII only.
"""
from __future__ import annotations

import pytest

from backend.services import link_redemptions, links_store

# --------------------------------------------------------------------------
# links[_<channel>]/{jti} -- the mint record. build_mint_record() is the ONE
# builder both the plain writer (record_mint) and the mint transaction
# (backend/routes/link_routes.py's _extra_writes) use -- see that function's
# own docstring for why there is only one.
# --------------------------------------------------------------------------

LINKS_MINT_RECORD_ALLOWED_KEYS = frozenset({
    "jti",
    "firm_id",
    "kit_id",
    "employee_id",
    "credit_cost",
    "cap_usd",
    "minted_at",
    "open_deadline",
    "status",
    "revoked_by",
    "revoked_at",
    "expire_at",
})


def test_links_mint_record_key_set():
    """Mutation: add a stray field to links_store.build_mint_record()'s
    return dict -- this goes red, since the check is an exact `==`, not a
    superset allowance."""
    record = links_store.build_mint_record(
        jti="jti-1", firm_id="acme", kit_id="i-90", employee_id="emp-1",
        credit_cost=5, cap_usd=1.5, open_deadline=1234567890,
    )
    assert set(record) == LINKS_MINT_RECORD_ALLOWED_KEYS, (
        "links mint record carries a key outside the pinned allowlist: {}. "
        "A new field here must be a deliberate, reviewed addition to "
        "LINKS_MINT_RECORD_ALLOWED_KEYS, not a silent pass -- it also "
        "widens the deployed data-at-rest inventory this test backs."
    ).format(set(record) - LINKS_MINT_RECORD_ALLOWED_KEYS)


def test_a_stray_key_on_the_mint_record_is_caught(monkeypatch):
    """Test the test (scar #9): prove the allowlist above can actually
    fail. Wrap build_mint_record so it returns one extra key, and confirm
    the allowlist check would flag it -- without touching production code,
    since links_store.py is outside this bead's declared edit surfaces."""
    real_builder = links_store.build_mint_record

    def _mutated(*args, **kwargs):
        record = real_builder(*args, **kwargs)
        record["_mutation_stray_key"] = "should be caught"
        return record

    record = _mutated(
        jti="jti-1", firm_id="acme", kit_id="i-90", employee_id="emp-1",
        credit_cost=5, cap_usd=1.5, open_deadline=1234567890,
    )
    assert set(record) != LINKS_MINT_RECORD_ALLOWED_KEYS, (
        "the allowlist check failed to catch an injected stray key -- it "
        "would pass a real regression silently"
    )


@pytest.mark.parametrize("missing_field", [
    "jti", "firm_id", "kit_id", "employee_id",
])
def test_mint_record_refuses_a_blank_identifier(missing_field):
    """A blank/None identifier must never reach the store as a written
    record -- pins the ValueError guard build_mint_record's own docstring
    names, parametrized over EVERY identifier field (scar #8: enumerate the
    set, not one instance)."""
    kwargs = dict(jti="jti-1", firm_id="acme", kit_id="i-90",
                  employee_id="emp-1", credit_cost=5, cap_usd=1.5,
                  open_deadline=1234567890)
    kwargs[missing_field] = ""
    with pytest.raises(ValueError):
        links_store.build_mint_record(**kwargs)


# --------------------------------------------------------------------------
# link_redemptions[_<channel>]/{jti} -- the AUTHORITATIVE "did anyone ever
# open this link" record (see credit_ledger.py's module docstring on why
# THIS store, not the links mirror's `status`, gates a refund).
# --------------------------------------------------------------------------

REDEMPTION_RECORD_ALLOWED_KEYS = frozenset({
    "jti",
    "firm_id",
    "kit_id",
    "opened_at",
    "completed_at",
})

# A THIRD writer of this SAME collection (found during bd polyglot-pdf-uaxt5's
# fresh-eyes follow-up, grepping for other callers of link_redemptions'
# underscore-private _collection): backend/services/link_spend.py's
# record_spend() imports link_redemptions._collection directly (its own
# module comment: "_collection and _enabled are underscore-private to
# link_redemptions, and this is a deliberate second caller") and adds
# `spend_usd` (a running Increment total) and, when turns > 0, `turns` --
# plus `spend_updated_at`, stamped on every call regardless of turns. This is
# the UNION allowlist for the LIVE inventory (a real deployed doc can carry
# these in addition to the base open/complete shape); the open/complete
# tests below keep asserting the NARROWER base set exactly, since neither of
# those two writers touches the spend fields.
REDEMPTION_RECORD_ALLOWED_KEYS_WITH_SPEND = REDEMPTION_RECORD_ALLOWED_KEYS | {
    "spend_usd", "turns", "spend_updated_at",
}


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, jti):
        self._store = store
        self._jti = jti

    def get(self):
        return _FakeSnapshot(self._store.get(self._jti))

    def set(self, data, merge=False):
        if merge and self._jti in self._store:
            self._store[self._jti].update(data)
        else:
            self._store[self._jti] = dict(data)

    def update(self, data):
        self._store[self._jti].update(data)


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, jti):
        return _FakeDocRef(self._store, jti)


@pytest.fixture
def fake_redemptions_store(monkeypatch):
    store: dict = {}
    monkeypatch.setenv(link_redemptions._ENABLED_ENV, "true")
    monkeypatch.setattr(link_redemptions, "_collection",
                        lambda *a, **k: _FakeCollection(store))
    # open_link's usage-rollup call is a side concern this file does not
    # pin -- stub it inert so a missing/misconfigured rollups module cannot
    # fail a store-shape test.
    monkeypatch.setattr(
        "backend.services.usage_rollups.record_link_opened",
        lambda *a, **k: None, raising=False,
    )
    return store


def test_link_redemption_record_key_set_on_first_open(fake_redemptions_store):
    """Mutation: add a stray field to link_redemptions.open_link()'s written
    dict -- this goes red on the exact-set check."""
    rec = link_redemptions.open_link(
        jti="jti-1", firm_id="acme", kit_id="i-90")
    assert set(rec) == REDEMPTION_RECORD_ALLOWED_KEYS, (
        "link_redemptions record carries a key outside the pinned "
        "allowlist: {}"
    ).format(set(rec) - REDEMPTION_RECORD_ALLOWED_KEYS)


def test_link_redemption_record_key_set_survives_completion(
        fake_redemptions_store, monkeypatch):
    """complete_link() only ever UPDATES completed_at on an existing
    record -- pin that it introduces no new key either, so the two writers
    of this doc (open_link, complete_link) cannot silently diverge in shape."""
    monkeypatch.setattr(
        "backend.services.usage_rollups.record_link_completed",
        lambda *a, **k: None, raising=False,
    )
    link_redemptions.open_link(jti="jti-2", firm_id="acme", kit_id="i-90")
    link_redemptions.complete_link(jti="jti-2")
    assert set(fake_redemptions_store["jti-2"]) == REDEMPTION_RECORD_ALLOWED_KEYS


def test_a_stray_key_on_the_redemption_record_is_caught(
        fake_redemptions_store):
    """Test the test: hand-inject a stray key into the fake store (bypassing
    the real writer) and confirm the allowlist check would flag it."""
    link_redemptions.open_link(jti="jti-3", firm_id="acme", kit_id="i-90")
    fake_redemptions_store["jti-3"]["_mutation_stray_key"] = "should be caught"
    assert set(fake_redemptions_store["jti-3"]) != REDEMPTION_RECORD_ALLOWED_KEYS


def test_link_spend_record_spend_stays_within_the_union_allowlist(
        fake_redemptions_store, monkeypatch):
    """link_spend.py's record_spend() is a THIRD writer of link_redemptions
    (imports _collection directly). Mutation: add a stray field to
    record_spend()'s `updates` dict -- this goes red on the exact-set check
    against the union allowlist."""
    from backend.services import link_spend

    class _FakeIncrement:
        """firebase_admin.firestore.Increment(x) -- record_spend() only
        needs a value it can store and later read back as a plain number
        for this test's purposes (the real SDK server-side-increments; this
        fake just stores the delta as the value, which is enough since no
        assertion here depends on the ACCUMULATED total)."""

        def __init__(self, value):
            self.value = value

    class _FakeFirestoreModule:
        Increment = _FakeIncrement

    import sys

    import firebase_admin
    fake_module = _FakeFirestoreModule()
    monkeypatch.setattr(firebase_admin, "firestore", fake_module,
                        raising=False)
    # `from firebase_admin import firestore` (link_spend.py's own inline
    # import) resolves a dotted submodule name through sys.modules FIRST
    # once the real firebase_admin.firestore has ever been imported by an
    # earlier test in the same session -- patching only the package
    # attribute above is invisible to that lookup path. Both must be
    # patched together, or this test is ORDER-DEPENDENT (passes alone,
    # fails after any test that has genuinely imported firebase_admin.
    # firestore first) -- exactly the get_settings()-style trap this repo
    # has hit before (see memory: get-settings-singleton-test-ordering-trap).
    monkeypatch.setitem(sys.modules, "firebase_admin.firestore", fake_module)

    # link_spend.py does `from backend.services.link_redemptions import
    # _collection` at MODULE LEVEL (a direct name binding into link_spend's
    # own namespace) -- so patching link_redemptions._collection (what
    # fake_redemptions_store already does) is invisible to link_spend's
    # OWN already-bound name. Patch it there too.
    monkeypatch.setattr(link_spend, "_collection",
                        lambda *a, **k: _FakeCollection(fake_redemptions_store))

    link_redemptions.open_link(jti="jti-4", firm_id="acme", kit_id="i-90")
    link_spend.record_spend(jti="jti-4", cost_usd=0.05, turns=2)

    rec = fake_redemptions_store["jti-4"]
    assert set(rec) <= REDEMPTION_RECORD_ALLOWED_KEYS_WITH_SPEND, (
        "link_spend.record_spend() wrote a key outside the union "
        "allowlist: {}"
    ).format(set(rec) - REDEMPTION_RECORD_ALLOWED_KEYS_WITH_SPEND)
    # And the spend fields ARE the ones actually added (not vacuously true
    # because record_spend wrote nothing).
    assert {"spend_usd", "turns", "spend_updated_at"} <= set(rec)


def test_a_stray_key_from_link_spend_is_caught(fake_redemptions_store):
    """Test the test: hand-inject a stray key past the union allowlist."""
    link_redemptions.open_link(jti="jti-5", firm_id="acme", kit_id="i-90")
    fake_redemptions_store["jti-5"]["_mutation_stray_key"] = "x"
    assert not (set(fake_redemptions_store["jti-5"])
               <= REDEMPTION_RECORD_ALLOWED_KEYS_WITH_SPEND)
