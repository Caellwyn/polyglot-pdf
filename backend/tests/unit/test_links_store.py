"""The mint record store (Epic 2 bead A1).

Pins the schema-only contract of backend/services/links_store.py: the
record_mint() write shape, the channel-explicit collection naming (mirroring
link_redemptions.py's pattern), get_link()'s None-vs-raise distinction, and
the TTL expire_at derivation. No transaction, no route wiring -- those land
in later Epic 2 beads (A2/A3/A5); this file pins only what THIS bead ships.

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
from datetime import datetime, timedelta, timezone

import pytest

import backend.services.links_store as links_store


class _FakeSnap:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self._doc_id = doc_id
        self.set_calls = []

    def get(self):
        return _FakeSnap(self._store.get(self._doc_id))

    def set(self, payload):
        self.set_calls.append(dict(payload))
        self._store[self._doc_id] = dict(payload)


class _FakeCollection:
    def __init__(self):
        self.store = {}
        self.doc_refs = {}
        self.limit_calls = []

    def document(self, doc_id):
        return self.doc_refs.setdefault(doc_id, _FakeDocRef(self.store, doc_id))

    def limit(self, n):
        self.limit_calls.append(n)
        return self

    def stream(self):
        return iter([])


class _FakeDB:
    def __init__(self):
        self.collections = {}
        self.asked = []

    def collection(self, name):
        self.asked.append(name)
        return self.collections.setdefault(name, _FakeCollection())


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)
    return db


# ------------------------------------------------------ collection naming


def test_the_demo_keeps_the_BARE_collection_name():
    """Mirrors link_redemptions.py's rule: renaming the demo's collection
    would orphan every mint record already written. Mutation: drop the
    DEFAULT_CHANNEL special-case -- red."""
    assert links_store._collection_name("demo") == "links"


def test_staging_gets_its_OWN_collection():
    """Mutation: return the bare name for every channel -- red."""
    assert links_store._collection_name("staging") == "links_staging"


def test_two_channels_never_share_a_collection():
    """The property, not just the pair. Mutation: hardcode a fixed suffix
    ignoring `channel` -- the set collapses and this goes red."""
    names = [links_store._collection_name(c)
              for c in ("demo", "staging", "pilot", "local")]
    assert len(set(names)) == len(names)


def test_collection_with_no_channel_arg_DEFAULTS_to_link_channel(
        fake_db, monkeypatch):
    """The public-backend contract: a caller that names no channel gets
    THIS process's own channel via link_channel(). Mutation: hardcode
    DEFAULT_CHANNEL as the fallback instead of calling link_channel() --
    red."""
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    links_store._collection()
    assert fake_db.asked == ["links_staging"]


def test_collection_with_no_channel_arg_and_UNSET_env_resolves_to_demo(
        fake_db, monkeypatch):
    """The companion case: an UNSET LINK_CHANNEL must not silently move the
    demo's collection -- link_channel() itself defaults to "demo", and
    _collection()'s no-argument default must chain through to that.
    Mutation: hardcode a non-demo fallback when channel is None -- red."""
    monkeypatch.delenv("LINK_CHANNEL", raising=False)
    links_store._collection()
    assert fake_db.asked == ["links"]


def test_an_explicit_channel_argument_OVERRIDES_link_channel(
        fake_db, monkeypatch):
    """A caller that DOES name a channel (the admin service) must not be
    silently redirected to this process's own LINK_CHANNEL. Mutation: ignore
    the `channel` parameter -- red."""
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    links_store._collection("demo")
    assert fake_db.asked == ["links"]


def test_collection_raises_when_db_is_none(monkeypatch):
    """A None db (get_db()'s own failure signal elsewhere in the codebase)
    must not be treated as usable. Mutation: drop the `db is None` guard --
    an AttributeError escapes instead of the documented exception, and this
    goes red."""
    monkeypatch.setattr("backend.services.auth.get_db", lambda: None)
    with pytest.raises(links_store.LinksStoreUnavailable):
        links_store._collection("demo")


# ------------------------------------------------------------ record_mint


def _mint(fake_db, channel=None, **over):
    kwargs = dict(
        jti="jti-1", firm_id="acme", kit_id="i-90", employee_id="uid-emp",
        credit_cost=1, cap_usd=3.0, open_deadline=2_000, now=1_000,
    )
    kwargs.update(over)
    return links_store.record_mint(channel=channel, **kwargs)


def test_record_mint_writes_the_full_schema(fake_db):
    """POSITIVE pin on the whole doc shape -- every field the plan names,
    nothing extra, nothing missing. Mutation: drop or rename any one field
    in the record dict -- red."""
    rec = _mint(fake_db, channel="demo")

    assert set(rec) == {
        "jti", "firm_id", "kit_id", "employee_id",
        # employee_email (bd polyglot-pdf-cpsi0): optional, None when the
        # caller (record_mint's own caller here) passes none.
        "employee_email",
        "credit_cost", "cap_usd",
        "minted_at", "open_deadline", "status", "revoked_by", "revoked_at",
        "expire_at",
    }
    assert rec["jti"] == "jti-1"
    assert rec["firm_id"] == "acme"
    assert rec["kit_id"] == "i-90"
    assert rec["employee_id"] == "uid-emp"
    assert rec["employee_email"] is None
    assert rec["credit_cost"] == 1
    assert rec["cap_usd"] == 3.0
    assert rec["minted_at"] == 1_000
    assert rec["open_deadline"] == 2_000
    assert rec["status"] == links_store.STATUS_MINTED
    assert rec["revoked_by"] is None
    assert rec["revoked_at"] is None


def test_record_mint_writes_to_the_named_channels_collection(fake_db):
    """The write must land in the CHANNEL-suffixed collection, not always
    the bare one. Mutation: call _collection() with no channel arg inside
    record_mint -- this goes red under a non-demo channel."""
    _mint(fake_db, channel="staging")

    col = fake_db.collections["links_staging"]
    assert "jti-1" in col.store
    assert col.store["jti-1"]["status"] == links_store.STATUS_MINTED


def test_record_mint_status_is_always_MINTED_on_write(fake_db):
    """Every mint starts at status=minted -- later beads (A3/A5) transition
    it, this bead only ever writes the starting state. Mutation: parametrize
    status as a caller argument or default it to something else -- red."""
    rec = _mint(fake_db, channel="demo")
    assert rec["status"] == "minted"


@pytest.mark.parametrize(
    "field,value",
    [("jti", ""), ("firm_id", ""), ("kit_id", ""), ("employee_id", ""),
     ("jti", None)],
)
def test_record_mint_refuses_missing_identity_fields(fake_db, field, value):
    """A blank/None identity field must refuse rather than write a broken
    record. Mutation: drop the `all(isinstance(...) and v ...)` guard --
    red."""
    with pytest.raises(ValueError):
        _mint(fake_db, channel="demo", **{field: value})
    assert fake_db.collections == {}


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_record_mint_refuses_non_positive_credit_cost(fake_db, bad):
    """A zero/negative/non-int credit_cost is a config bug, not a valid
    mint -- refuse rather than record a broken snapshot. `bool` is excluded
    explicitly since True/False are ints in Python and would otherwise slip
    through isinstance(v, int). Mutation: drop the credit_cost guard --
    red."""
    with pytest.raises(ValueError):
        _mint(fake_db, channel="demo", credit_cost=bad)
    assert fake_db.collections == {}


@pytest.mark.parametrize("bad", [0, -1.0, True])
def test_record_mint_refuses_non_positive_cap_usd(fake_db, bad):
    """Mirrors the credit_cost guard for cap_usd -- a link with no spend
    ceiling is a configuration bug. Mutation: drop the cap_usd guard --
    red."""
    with pytest.raises(ValueError):
        _mint(fake_db, channel="demo", cap_usd=bad)
    assert fake_db.collections == {}


def test_record_mint_raises_LinksStoreUnavailable_on_store_failure(monkeypatch):
    """A write failure (IAM drift, network) must surface as the documented
    exception, not an arbitrary one a caller does not expect. Mutation: let
    the raw exception propagate -- red."""
    def _boom():
        raise RuntimeError("firestore down")

    monkeypatch.setattr("backend.services.auth.get_db", _boom)
    with pytest.raises(links_store.LinksStoreUnavailable):
        _mint(None, channel="demo")


# ---------------------------------------------------------------- get_link


def test_get_link_returns_none_for_a_missing_doc(fake_db):
    """A never-minted jti is a legitimate 'no record' answer, not a store
    failure -- returns None, does not raise. Mutation: raise instead of
    returning None on a missing doc -- red."""
    assert links_store.get_link("nope", channel="demo") is None


def test_get_link_returns_the_stored_record(fake_db):
    """POSITIVE pin: the round trip through record_mint -> get_link.
    Mutation: return {} unconditionally -- red."""
    _mint(fake_db, channel="demo")
    rec = links_store.get_link("jti-1", channel="demo")
    assert rec["jti"] == "jti-1"
    assert rec["status"] == "minted"


def test_get_link_raises_on_store_failure(monkeypatch):
    """A store outage must raise LinksStoreUnavailable, not silently answer
    None -- conflating 'never minted' with 'cannot tell' would let the A3
    open-requires-a-record gate admit a link during an outage instead of
    refusing it. Mutation: catch the exception and return None -- red."""
    def _boom():
        raise RuntimeError("firestore down")

    monkeypatch.setattr("backend.services.auth.get_db", _boom)
    with pytest.raises(links_store.LinksStoreUnavailable):
        links_store.get_link("jti-1", channel="demo")


def test_get_link_reads_from_the_named_channels_collection(fake_db):
    """A record minted on staging must not be visible when reading the demo
    collection. Mutation: always read the bare collection -- red."""
    _mint(fake_db, channel="staging")
    assert links_store.get_link("jti-1", channel="demo") is None
    assert links_store.get_link("jti-1", channel="staging") is not None


# ----------------------------------------------------------------- expire_at


def test_expire_at_for_adds_the_retention_margin():
    """The TTL field is open_deadline PLUS the retention margin, not the
    deadline itself -- writing the bare deadline would let Firestore reap a
    just-opened link's record before the admin console can show it.
    Mutation: return the deadline unmodified -- red."""
    deadline = 1_700_000_000
    result = links_store.expire_at_for(deadline)

    expected = (
        datetime.fromtimestamp(deadline, tz=timezone.utc)
        + timedelta(seconds=links_store._TTL_RETENTION_MARGIN_S)
    )
    assert result == expected
    assert result > datetime.fromtimestamp(deadline, tz=timezone.utc)


def test_expire_at_for_is_timezone_aware_utc():
    """A naive datetime is ambiguous to Firestore's TTL policy and to any
    later comparison against another aware timestamp. Mutation: build the
    result with datetime.fromtimestamp(deadline) (no tz) -- red."""
    result = links_store.expire_at_for(1_700_000_000)
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)


def test_record_mint_expire_at_matches_expire_at_for(fake_db):
    """The written record's expire_at must be DERIVED from open_deadline via
    expire_at_for, not an independent computation that could drift from it.
    Mutation: compute expire_at inline with a different margin inside
    record_mint -- red."""
    rec = _mint(fake_db, channel="demo", open_deadline=5_000)
    assert rec["expire_at"] == links_store.expire_at_for(5_000)


# ------------------------------------------------------------- status probe


def test_links_store_status_ok_and_read_shaped(fake_db):
    """READ-shaped (limit-1 stream), never write+delete -- probing with a
    write would test the wrong IAM grant. Mutation: switch the probe to a
    write+delete shape -- the no-writes assertion goes red."""
    assert links_store.links_store_status(channel="demo") == "ok"

    col = fake_db.collections["links"]
    assert col.limit_calls == [1]
    assert all(not ref.set_calls for ref in col.doc_refs.values())


def test_links_store_status_reports_error(monkeypatch):
    """Mutation: swallow the exception into 'ok' -- red."""
    def _boom():
        raise RuntimeError("iam drift")

    monkeypatch.setattr("backend.services.auth.get_db", _boom)
    assert links_store.links_store_status(channel="demo").startswith("error:")


# --------------------------------------------------------- status constants


def test_all_statuses_lists_every_named_status_constant():
    """ALL_STATUSES is the set the plan names for the `status` field
    (minted/opened/completed/refunded/revoked/budget_exhausted) -- a later
    caller enumerating legal transitions needs the complete set in one
    place, not a hand-copied list that can drift. Mutation: drop one status
    from ALL_STATUSES -- red."""
    assert set(links_store.ALL_STATUSES) == {
        "minted", "opened", "completed", "refunded", "revoked",
        "budget_exhausted",
    }
    assert len(links_store.ALL_STATUSES) == len(set(links_store.ALL_STATUSES))
