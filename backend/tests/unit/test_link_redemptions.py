"""The redemption store's REAL logic (bd polyglot-pdf-ugm6).

Fresh-eyes r4: every test touching one-time use monkeypatched `open_link` at
its CALL SITE, so the actual function -- and the `_enabled()` fail-closed
gate the whole guarantee rests on -- never executed. The full backend suite
stayed green regardless of what this module did.

That is the shape CLAUDE.md scar #8 warns about: a guard that reads correctly
and is documented prominently, verified only through a stand-in that behaves
correctly by construction. These tests drive the real functions.

THE SCENARIO THAT MOTIVATES THEM: an operator turns on LINK_MINTING_ENABLED
(the bd ik7e rollout) and forgets LINK_REDEMPTIONS_FIRESTORE_ENABLED. That
must refuse every open -- a link with no redemption store is an unbounded
replay hole -- and it must refuse LOUDLY rather than crash somewhere the
caller does not expect.

ASCII only.
"""
import pytest

from backend.services import link_redemptions as lrd
from backend.services.link_redemptions import (
    LinkAlreadyUsed,
    RedemptionUnavailable,
    complete_link,
    open_link,
)


class _Doc:
    def __init__(self, store, jti):
        self._store, self._jti = store, jti

    def get(self):
        return _Snap(self._store.get(self._jti))

    def set(self, rec):
        self._store[self._jti] = dict(rec)

    def update(self, patch):
        if self._jti not in self._store:
            raise RuntimeError("no such document")
        self._store[self._jti].update(patch)


class _Snap:
    def __init__(self, rec):
        self._rec = rec

    @property
    def exists(self):
        return self._rec is not None

    def to_dict(self):
        return dict(self._rec) if self._rec else None


class _Collection:
    def __init__(self, store):
        self._store = store

    def document(self, jti):
        return _Doc(self._store, jti)


@pytest.fixture
def store(monkeypatch):
    """Enable the module and give it a Firestore-shaped collection."""
    data = {}
    monkeypatch.setenv("LINK_REDEMPTIONS_FIRESTORE_ENABLED", "true")
    monkeypatch.setattr(lrd, "_collection", lambda: _Collection(data))
    return data


# --- the fail-closed gate, which had no test at all --------------------------


def test_the_store_is_DISABLED_by_default(monkeypatch):
    """A deployment that has not provisioned Firestore must not silently
    treat every link as fresh. Mutation: default the env var to "true" --
    red."""
    monkeypatch.delenv("LINK_REDEMPTIONS_FIRESTORE_ENABLED", raising=False)
    assert lrd._enabled() is False


@pytest.mark.parametrize(
    "value, enabled",
    [("true", True), ("TRUE", True), ("True", True),
     ("false", False), ("", False), ("1", False), ("yes", False),
     ("truthy", False)],
)
def test_only_an_explicit_true_enables_the_store(monkeypatch, value, enabled):
    """Pinned per-value, not just the happy case: a comparison flipped to
    `!= "false"` would enable the store for "1", "yes", and "truthy", which
    an operator could plausibly set.

    Mutation: `!= "false"` instead of `== "true"` -- the "1"/"yes"/"truthy"
    cases go red.
    """
    monkeypatch.setenv("LINK_REDEMPTIONS_FIRESTORE_ENABLED", value)
    assert lrd._enabled() is enabled


def test_a_DISABLED_store_REFUSES_rather_than_admitting(monkeypatch):
    """THE OPERATOR SCENARIO: minting on, redemption store not provisioned.
    Refusing every open is correct -- a link with no store behind it is an
    unbounded replay hole -- and it must raise the exception the CALLERS
    handle, not an arbitrary one.

    Mutation: `return {}` instead of raising -- red.
    """
    monkeypatch.delenv("LINK_REDEMPTIONS_FIRESTORE_ENABLED", raising=False)

    with pytest.raises(RedemptionUnavailable):
        open_link("jti-1", "firm-a", "i-90")


# --- the real open/complete cycle --------------------------------------------


def test_the_first_open_writes_a_record_with_NO_client_identifier(store):
    """The record's field set is CLOSED, like the token's: we hold the
    pseudonym, the firm holds identity. Mutation: add an email/name field --
    red."""
    rec = open_link("jti-1", "firm-a", "i-90", now=1_000)

    assert set(rec) == {"jti", "firm_id", "kit_id", "opened_at", "completed_at"}
    assert rec["opened_at"] == 1_000
    assert rec["completed_at"] is None


def test_reopening_an_UNFINISHED_link_returns_the_ORIGINAL_open_time(store):
    """The completion clock must not restart on every reopen -- otherwise a
    client could hold a link open indefinitely by refreshing, and the 7-day
    window would never actually expire.

    Mutation: overwrite opened_at on reopen -- red.
    """
    open_link("jti-1", "firm-a", "i-90", now=1_000)
    again = open_link("jti-1", "firm-a", "i-90", now=500_000)

    assert again["opened_at"] == 1_000, "the completion clock must not restart"


def test_a_COMPLETED_link_starts_no_NEW_session(store):
    """One completion per link -- what that BOUNDS is a new BACKEND
    CONNECTION, i.e. a new paid session (maintainer, 2026-08-24: "The TTL
    should be backend connection").

    open_link is now called only from paths where a refusal is correct: the
    socket, /open, and the paid TTS routes. Retrieval (download, print,
    preview) does not reach here at all, so this refusal costs the client
    nothing they already own.

    Mutation: drop the completed_at check -- red.
    """
    open_link("jti-1", "firm-a", "i-90", now=1_000)
    complete_link("jti-1", now=2_000)

    with pytest.raises(LinkAlreadyUsed):
        open_link("jti-1", "firm-a", "i-90", now=2_060)


def test_complete_link_is_BEST_EFFORT_and_never_raises(store, monkeypatch):
    """Asymmetric by design: failing to RECORD a completion costs one extra
    reopen of a form already finished, while failing to BLOCK an open costs a
    second paid session. So completion absorbs its failure and open refuses.

    Mutation: let the exception propagate -- red (a store failure at session
    end would then surface as a crash on the client's completed form).
    """
    def _boom():
        raise RuntimeError("firestore down")

    monkeypatch.setattr(lrd, "_collection", _boom)

    complete_link("jti-1")   # must not raise


def test_a_store_failure_during_open_becomes_RedemptionUnavailable(
    store, monkeypatch
):
    """Callers refuse on RedemptionUnavailable specifically. A raw exception
    escaping would bypass their fail-closed handling and surface as a 500 (or
    an unhandled crash on the socket).

    Mutation: let the raw exception propagate -- red.
    """
    def _boom():
        raise RuntimeError("firestore down")

    monkeypatch.setattr(lrd, "_collection", _boom)

    with pytest.raises(RedemptionUnavailable):
        open_link("jti-1", "firm-a", "i-90")


def test_LinkAlreadyUsed_is_not_swallowed_by_the_generic_handler(store):
    """The broad `except Exception` that wraps store failures must not
    convert an ALREADY-USED verdict into "store unavailable" -- both refuse,
    but only one of them is a real answer, and conflating them would hide a
    replay behind an infrastructure warning in the logs.

    Mutation: remove LinkAlreadyUsed from the re-raise tuple -- red.
    """
    open_link("jti-1", "firm-a", "i-90", now=1_000)
    complete_link("jti-1", now=2_000)

    with pytest.raises(LinkAlreadyUsed):
        open_link("jti-1", "firm-a", "i-90", now=3_000)


def test_separate_links_do_not_interfere(store):
    """Records are keyed by jti; completing one link must not burn another."""
    open_link("jti-1", "firm-a", "i-90", now=1_000)
    open_link("jti-2", "firm-a", "i-90", now=1_000)
    complete_link("jti-1", now=2_000)

    assert open_link("jti-2", "firm-a", "i-90", now=3_000)["completed_at"] is None


# --- the shared gate both doors call ----------------------------------------


def _claims(cw=7 * 24 * 3600, jti="jti-1"):
    return {"jti": jti, "firm_id": "firm-a", "link_kit_id": "i-90",
            "employee_id": "u-emp-7", "cw": cw, "is_client_link": True}


def test_the_gate_admits_a_fresh_unburned_link(store):
    from backend.services.link_redemptions import enforce_link_redemption

    rec = enforce_link_redemption(_claims(), now=1_000)

    assert rec["jti"] == "jti-1"
    assert rec["completed_at"] is None


def test_the_gate_refuses_a_link_past_its_completion_window(store):
    """Mutation: drop the `stamp >= opened_at + window` check -- red."""
    from backend.services.link_redemptions import (
        LinkWindowElapsed,
        enforce_link_redemption,
    )

    enforce_link_redemption(_claims(cw=3600), now=1_000)

    with pytest.raises(LinkWindowElapsed):
        enforce_link_redemption(_claims(cw=3600), now=1_000 + 3601)


@pytest.mark.parametrize(
    "bad_cw", [None, 0, -1, "week", True, 1.5],
    ids=["missing", "zero", "negative", "string", "bool", "float"],
)
def test_a_credential_with_NO_USABLE_WINDOW_is_refused(store, bad_cw):
    """FAIL CLOSED on an uncheckable credential.

    Found by mutation: returning the record instead of raising here left the
    whole suite green. A claims dict with no usable `cw` cannot have its
    completion window checked at all, so admitting it restores exactly the
    hole this gate exists to close -- and `cw` is attacker-adjacent, since it
    rides the token payload.

    Mutation: `return record` instead of raising -- red.
    """
    from backend.services.link_redemptions import (
        LinkWindowElapsed,
        enforce_link_redemption,
    )

    with pytest.raises(LinkWindowElapsed):
        enforce_link_redemption(_claims(cw=bad_cw), now=1_000)


def test_the_gate_refuses_a_COMPLETED_link(store):
    from backend.services.link_redemptions import (
        LinkAlreadyUsed,
        complete_link,
        enforce_link_redemption,
    )

    enforce_link_redemption(_claims(), now=1_000)
    complete_link("jti-1", now=2_000)

    with pytest.raises(LinkAlreadyUsed):
        enforce_link_redemption(_claims(), now=3_000)


@pytest.mark.parametrize(
    "stored_at, why",
    [
        (0, "an epoch stamp computes a deadline in 1970 and would lock out a "
            "client who JUST opened their link"),
        (-1, "a negative stamp is the same failure with a different shape"),
        (10_000_000_000, "a FAR-FUTURE stamp would extend the completion "
                         "window indefinitely -- the other direction, and the "
                         "one the docstring promised while no test fed it"),
    ],
    ids=["epoch", "negative", "far-future"],
)
def test_the_gate_tolerates_an_IMPLAUSIBLE_stored_open_time(
    store, monkeypatch, stored_at, why
):
    """A corrupt stamp must not lock out a client who just opened their link,
    NOR extend the window forever.

    Both directions are now exercised. Opus r10 found the far-future half
    deletable -- removing `or opened_at > stamp + 300` left 114 link tests
    green, because every case fed 0. The property was asserted in prose and
    nowhere in code.

    Mutation, per parametrization: drop the `<= 0` half -> epoch/negative
    red; drop the `> stamp + 300` half -> far-future red.
    """
    from backend.services.link_redemptions import enforce_link_redemption

    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": stored_at, "completed_at": None,
        },
    )

    now = 1_000_000
    # The gate ADMITS it, falling back to NOW rather than trusting the stamp
    # -- so a corrupt record never locks out a client mid-form.
    record = enforce_link_redemption(_claims(cw=3600), now=now)
    assert record, why

    # And it REPLACES the stamp with the fallback rather than passing the
    # corrupt value through. That is the assertion that covers BOTH
    # directions: an epoch stamp would compute a 1970 deadline, a far-future
    # one an unbounded window, and neither survives.
    assert record["opened_at"] == now, why


# --- channel isolation of the LEDGER (bd polyglot-pdf-3q9qn) ----------------
#
# The token's `aud` claim stops a staging link OPENING on the demo. It does
# NOT stop the two channels writing over each other's ledger: the burn is
# recorded under the jti alone, so a shared collection means a staging
# test-drive marks a DEMO link used and the client finds a dead link.
#
# These drive the real _collection_name(). The FakeCollection above ignores the
# name it is given, so a test that went through it would pass no matter what
# this function returned -- exactly the stand-in trap this file's own header
# warns about, and it left this surface unpinned on the first attempt.


def test_the_demo_keeps_the_BARE_collection_name(monkeypatch):
    """Renaming the demo's collection would orphan every burn already recorded."""
    monkeypatch.setenv("LINK_CHANNEL", "demo")
    assert lrd._collection_name() == "link_redemptions"


def test_an_UNSET_channel_also_keeps_the_bare_name(monkeypatch):
    """The default must not silently move the demo's ledger."""
    monkeypatch.delenv("LINK_CHANNEL", raising=False)
    assert lrd._collection_name() == "link_redemptions"


def test_staging_gets_its_OWN_collection(monkeypatch):
    """The isolation itself."""
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    assert lrd._collection_name() == "link_redemptions_staging"


def test_two_channels_never_share_a_collection(monkeypatch):
    """The PROPERTY, not the two names.

    Asserting only the literal pair would pass if a third channel collided
    with either -- and channels are added by setting one env var.
    """
    names = []
    for channel in ("demo", "staging", "pilot", "local"):
        monkeypatch.setenv("LINK_CHANNEL", channel)
        names.append(lrd._collection_name())

    assert len(set(names)) == len(names), (
        f"two channels share a redemption collection: {names} -- a burn in one "
        "would mark the other's link used"
    )


def test_the_real_collection_accessor_ASKS_FIRESTORE_for_the_channel_name(
        monkeypatch):
    """The one line that wires _collection_name() into Firestore.

    Every other test in this file monkeypatches `_collection` wholesale, so
    reverting `db.collection(_collection_name())` to `db.collection(COLLECTION)`
    left the ENTIRE 4390-test suite green while silently restoring the shared
    ledger. Pinning the pure function was not enough -- nothing proved the
    production path ever called it.

    So this drives the real `_collection()` with a recording client and asserts
    the NAME Firestore is actually asked for.
    """
    asked: list[str] = []

    class _RecordingDb:
        def collection(self, name):
            asked.append(name)
            return object()

    monkeypatch.setenv("LINK_REDEMPTIONS_FIRESTORE_ENABLED", "true")
    monkeypatch.setattr("backend.services.auth.get_db", lambda: _RecordingDb())

    monkeypatch.setenv("LINK_CHANNEL", "staging")
    lrd._collection()
    monkeypatch.setenv("LINK_CHANNEL", "demo")
    lrd._collection()

    assert asked == ["link_redemptions_staging", "link_redemptions"], (
        f"the collection accessor asked Firestore for {asked} -- the channel "
        "name is not reaching the query, so both channels share one ledger"
    )
