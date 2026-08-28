"""Per-firm monthly link metering (bd polyglot-pdf-ik7e).

The property that matters most is NEGATIVE: this must never refuse a mint.
The allowance is a subscription tier ($500/mo for 30, then $15 each), not an
abuse limit -- a firm minting link 31 has paid for it. Everything else here is
reporting.
"""

import time

import pytest

from backend.services import link_metering


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Ref:
    def __init__(self, store, key):
        self._store, self._key = store, key

    def get(self):
        if self._store.read_error:
            raise RuntimeError(self._store.read_error)
        return _Snap(self._store.docs.get(self._key))

    def set(self, updates, merge=False):
        if self._store.write_error:
            raise RuntimeError(self._store.write_error)
        rec = self._store.docs.setdefault(self._key, {}) if merge else {}
        for field, value in updates.items():
            rec[field] = rec.get(field, 0) + value.value if hasattr(value, "value") else value
        self._store.docs[self._key] = rec


class _Store:
    def __init__(self):
        self.docs = {}
        self.read_error = None
        self.write_error = None


@pytest.fixture
def store(monkeypatch):
    s = _Store()
    monkeypatch.setattr(
        link_metering, "_usage_doc", lambda firm, period: _Ref(s, f"{firm}/{period}")
    )
    monkeypatch.delenv("LINK_FIRM_CAP", raising=False)
    return s


# ---------------------------------------------------------------------------
# The negative property: metering NEVER refuses
# ---------------------------------------------------------------------------


def test_a_firm_OVER_its_allowance_still_mints(store):
    """31 links on a 30 allowance: counted and flagged, NOT refused.

    A firm on pay-as-you-go has paid for link 31. Refusing it would break a
    paying customer over a number the maintainer called provisional.
    """
    for _ in range(31):
        usage = link_metering.record_mint("firm-a")
    assert usage["minted"] == 31
    assert usage["allowance"] == 30
    assert usage["over_allowance"] is True   # billable, not blocked


def test_an_unwritable_store_does_not_break_minting(store):
    """A billing miscount costs an invoice line; a refused mint costs a form."""
    store.write_error = "firestore down"
    usage = link_metering.record_mint("firm-a")   # must not raise
    assert usage["over_allowance"] is False


def test_an_unreadable_count_reports_zero_rather_than_raising(store):
    store.read_error = "firestore down"
    assert link_metering.links_minted_this_period("firm-a") == 0


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


def test_mints_accumulate_within_a_period(store):
    for _ in range(3):
        link_metering.record_mint("firm-a")
    assert link_metering.links_minted_this_period("firm-a") == 3


def test_each_firm_is_metered_SEPARATELY(store):
    link_metering.record_mint("firm-a")
    link_metering.record_mint("firm-a")
    link_metering.record_mint("firm-b")
    assert link_metering.links_minted_this_period("firm-a") == 2
    assert link_metering.links_minted_this_period("firm-b") == 1


def test_a_firm_with_no_mints_reads_zero(store):
    assert link_metering.links_minted_this_period("never-minted") == 0


def test_a_firm_UNDER_its_allowance_is_not_flagged(store):
    usage = link_metering.record_mint("firm-a")
    assert usage["minted"] == 1
    assert usage["over_allowance"] is False


def test_exactly_AT_the_allowance_is_not_yet_over(store):
    """30 of 30 is included in the subscription; 31 is the first billable."""
    for _ in range(30):
        usage = link_metering.record_mint("firm-a")
    assert usage["minted"] == 30
    assert usage["over_allowance"] is False


# ---------------------------------------------------------------------------
# The billing PERIOD
# ---------------------------------------------------------------------------


def test_the_period_is_a_calendar_month_in_UTC():
    """A bucket that moves with the server timezone double-counts."""
    jan = time.mktime((2026, 1, 15, 12, 0, 0, 0, 0, 0))
    assert link_metering.billing_period(
        time.mktime(time.gmtime(jan))
    ).startswith("2026-01")
    assert link_metering.billing_period(0) == "1970-01"


def test_a_NEW_month_starts_a_fresh_count(store, monkeypatch):
    """The allowance is monthly, so February must not inherit January."""
    monkeypatch.setattr(link_metering, "billing_period", lambda now=None: "2026-01")
    for _ in range(30):
        link_metering.record_mint("firm-a")
    assert link_metering.links_minted_this_period("firm-a") == 30

    monkeypatch.setattr(link_metering, "billing_period", lambda now=None: "2026-02")
    assert link_metering.links_minted_this_period("firm-a") == 0
    usage = link_metering.record_mint("firm-a")
    assert usage["minted"] == 1
    assert usage["over_allowance"] is False


def test_the_allowance_is_tunable(store, monkeypatch):
    """Tiers are provisional -- the number must move without a code change."""
    monkeypatch.setenv("LINK_FIRM_CAP", "100")
    for _ in range(31):
        usage = link_metering.record_mint("firm-a")
    assert usage["allowance"] == 100
    assert usage["over_allowance"] is False


def test_a_corrupt_count_reads_as_zero(store):
    for bad in ("many", None, True, [], 3.5, -2):
        store.docs["firm-x/" + link_metering.billing_period()] = {
            link_metering.MINTED_FIELD: bad
        }
        assert link_metering.links_minted_this_period("firm-x") == 0


# ---------------------------------------------------------------------------
# WIRING -- a meter nobody calls counts nothing
# ---------------------------------------------------------------------------


def test_the_MINT_ROUTE_actually_calls_the_meter():
    """Derived from the shipped source, so deleting the call reddens here.

    Counting must happen at MINT: the redemption record is only created when a
    CLIENT OPENS a link, so a count taken from documents would miss every
    minted-but-unopened link -- exactly the ones the firm was billed for.
    """
    from pathlib import Path as _P

    src = _P(link_metering.__file__).parent.parent / "routes" / "link_routes.py"
    body = src.read_text(encoding="utf-8")
    assert "record_mint(firm_id)" in body, (
        "the mint route no longer meters -- a firm's link usage would read "
        "zero forever"
    )


def test_the_mint_route_does_NOT_gate_on_the_meter():
    """The meter reports; it must not refuse.

    Guards the misreading a future author is most likely to make ("it is a
    cap, so cap it"), which would break a paying customer on link 31.
    """
    from pathlib import Path as _P

    src = _P(link_metering.__file__).parent.parent / "routes" / "link_routes.py"
    body = src.read_text(encoding="utf-8")
    after = body[body.index("record_mint(firm_id)"):]
    window = after[: after.index("return MintLinkResponse")]
    assert "raise HTTPException" not in window, (
        "the mint route now REFUSES based on the meter. The allowance is a "
        "subscription tier, not an abuse limit: link 31 has been paid for."
    )
