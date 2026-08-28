"""Per-link spend accumulation and the ceiling (bd polyglot-pdf-ik7e).

The properties that matter, in order:

  1. spend SURVIVES a reconnect. This is the entire reason the ceiling keys on
     the signed jti rather than the browser-generated form_session_id -- a
     ceiling a client can reset by refreshing the page is not a ceiling.
  2. an unreachable store REFUSES, and never reads as "spent nothing".
  3. a failed WRITE does not kill a live session (the deliberate asymmetry).
  4. staff sessions are not subject to it at all.
"""

import pytest

from backend.services import link_spend
from backend.services.link_redemptions import RedemptionUnavailable


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Doc:
    """A fake Firestore document that ACTUALLY APPLIES Increment.

    A fake that merely records the call would let a broken increment pass: the
    point of the store is that repeated writes ACCUMULATE, so the fake has to
    accumulate too or the reconnect test proves nothing.
    """

    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self):
        if self._store.read_error:
            raise RuntimeError(self._store.read_error)
        return _Snap(self._store.docs.get(self._key))

    def update(self, updates):
        if self._store.write_error:
            raise RuntimeError(self._store.write_error)
        rec = self._store.docs.setdefault(self._key, {})
        for field, value in updates.items():
            if hasattr(value, "value"):          # firestore.Increment
                rec[field] = rec.get(field, 0) + value.value
            else:
                rec[field] = value
        self._store.writes.append(dict(updates))


class _Store:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.writes = []
        self.read_error = None
        self.write_error = None

    def document(self, key):
        return _Doc(self, key)


@pytest.fixture
def store(monkeypatch):
    s = _Store()
    monkeypatch.setattr(link_spend, "_enabled", lambda: True)
    monkeypatch.setattr(link_spend, "_collection", lambda: s)
    monkeypatch.delenv("LINK_COST_CEILING_USD", raising=False)
    return s


# ---------------------------------------------------------------------------
# 1. The reconnect property -- why the key is the signed jti
# ---------------------------------------------------------------------------


def test_spend_ACCUMULATES_across_reconnects(store):
    """Three sessions on one link add up. A per-connection counter would not.

    This is the hole the bead named: live_ai_gemini resets its cost counter in
    _run_session_loop, which runs once per CONNECTION, so today a reconnect
    starts from zero.
    """
    for _ in range(3):
        link_spend.record_spend("jti-a", 1.25, turns=10)
    assert link_spend.spend_so_far("jti-a") == pytest.approx(3.75)
    assert store.docs["jti-a"][link_spend.TURNS_FIELD] == 30


def test_a_DIFFERENT_link_has_its_own_budget(store):
    link_spend.record_spend("jti-a", 4.0)
    link_spend.record_spend("jti-b", 0.5)
    assert link_spend.spend_so_far("jti-a") == pytest.approx(4.0)
    assert link_spend.spend_so_far("jti-b") == pytest.approx(0.5)


def test_an_unknown_link_has_spent_nothing(store):
    assert link_spend.spend_so_far("never-seen") == 0.0


# ---------------------------------------------------------------------------
# 2. The ceiling
# ---------------------------------------------------------------------------


def test_a_link_UNDER_its_ceiling_is_allowed_and_reports_headroom(store):
    link_spend.record_spend("jti-a", 4.0)
    assert link_spend.check_budget("jti-a") == pytest.approx(6.0)


def test_a_link_AT_its_ceiling_is_refused(store):
    """>= not >: at exactly $10 of a $10 ceiling there is no room left."""
    link_spend.record_spend("jti-a", 10.0)
    with pytest.raises(link_spend.LinkBudgetExhausted):
        link_spend.check_budget("jti-a")


def test_a_link_OVER_its_ceiling_is_refused(store):
    link_spend.record_spend("jti-a", 12.34)
    with pytest.raises(link_spend.LinkBudgetExhausted):
        link_spend.check_budget("jti-a")


def test_a_PER_FORM_ceiling_is_honoured(store):
    """The per-form room: $5 on this kit refuses what $10 would allow."""
    link_spend.record_spend("jti-a", 6.0)
    link_spend.check_budget("jti-a")  # fine under the $10 default
    with pytest.raises(link_spend.LinkBudgetExhausted):
        link_spend.check_budget("jti-a", {"link_cost_ceiling_usd": 5})


def test_a_retuned_env_ceiling_takes_effect(store, monkeypatch):
    link_spend.record_spend("jti-a", 6.0)
    monkeypatch.setenv("LINK_COST_CEILING_USD", "5")
    with pytest.raises(link_spend.LinkBudgetExhausted):
        link_spend.check_budget("jti-a")


# ---------------------------------------------------------------------------
# 3. Failure polarity
# ---------------------------------------------------------------------------


def test_an_unreachable_store_REFUSES_rather_than_reading_as_zero(store):
    """"We cannot tell" must never resolve to "nothing spent"."""
    store.read_error = "firestore unavailable"
    with pytest.raises(RedemptionUnavailable):
        link_spend.spend_so_far("jti-a")
    with pytest.raises(RedemptionUnavailable):
        link_spend.check_budget("jti-a")


def test_a_DISABLED_store_defers_to_the_REDEMPTION_gate(store, monkeypatch):
    """A switched-off store is not a spend question, and this must not refuse.

    enforce_link_redemption already fails closed on exactly this condition and
    runs FIRST on every paid door, so a client-link session cannot reach the
    spend check with the store disabled. Refusing here too would be a second
    refusal for one condition -- and would break local dev and any test that
    stubs the redemption path, which is how this was caught (4 socket tests
    went red).

    The invariant this pins is therefore: the ADMITTING door is the one that
    fails closed.
    """
    monkeypatch.setattr(link_spend, "_enabled", lambda: False)
    assert link_spend.spend_so_far("jti-a") == 0.0
    assert link_spend.check_budget("jti-a") == 10.0  # full headroom, no refusal

    # ...and the gate that DOES refuse is still fail-closed on the same flag.
    from backend.services import link_redemptions

    monkeypatch.setattr(link_redemptions, "_enabled", lambda: False)
    with pytest.raises(RedemptionUnavailable):
        link_redemptions.open_link("jti-a", "firm-a", "i-90")


def test_a_failed_WRITE_does_not_raise_into_a_live_session(store):
    """The deliberate asymmetry: reads refuse, writes degrade.

    The client is mid-sentence and the spend is already incurred; dropping them
    for a bookkeeping error costs a real person their work. The next check_budget
    still refuses, so the ceiling holds within one session's overrun.
    """
    store.write_error = "firestore unavailable"
    link_spend.record_spend("jti-a", 3.0)  # must not raise


def test_a_corrupt_spend_value_reads_as_zero_not_as_a_crash(store):
    """A hand-edited or half-written field must not 500 the socket."""
    for bad in ("lots", None, True, [], {"a": 1}, -5):
        store.docs["jti-x"] = {link_spend.SPEND_FIELD: bad}
        assert link_spend.spend_so_far("jti-x") == 0.0


# ---------------------------------------------------------------------------
# 4. Scope + hygiene
# ---------------------------------------------------------------------------


def test_a_session_with_NO_jti_records_nothing(store):
    """Staff have no jti and are not the abuse surface this defends."""
    link_spend.record_spend("", 5.0)
    link_spend.record_spend(None, 5.0)
    assert store.writes == []


def test_a_zero_or_negative_cost_is_not_recorded(store):
    link_spend.record_spend("jti-a", 0.0)
    link_spend.record_spend("jti-a", -1.0)
    assert store.writes == []


def test_the_spend_record_carries_NO_client_identity(store):
    """Same privacy invariant as the redemption record: jti only, never a person."""
    link_spend.record_spend("jti-a", 1.0, turns=3)
    written = store.docs["jti-a"]
    assert set(written) <= {
        link_spend.SPEND_FIELD,
        link_spend.TURNS_FIELD,
        "spend_updated_at",
    }


def test_it_shares_the_redemption_stores_accessor(store):
    """Pins the deliberate private import.

    The spend fields live on link_redemptions' own documents. If that module
    renames _collection or _enabled, this must fail loudly here rather than
    writing to a second, divergent collection.
    """
    from backend.services import link_redemptions

    assert hasattr(link_redemptions, "_collection")
    assert hasattr(link_redemptions, "_enabled")


# ---------------------------------------------------------------------------
# THE SECTION-SWITCH TRAP -- found by Opus cross-surface review, 2026-08-27
# ---------------------------------------------------------------------------


def test_the_cost_counter_SURVIVES_a_section_switch():
    """A section switch must not zero the spend the ceiling is about to bank.

    THE BUG THIS PINS: form_filling_service._switch_to_section_locked calls
    finalize() then start_session() on the SAME adapter, without dropping the
    WebSocket. start_session re-enters _run_session_loop, which zeroes
    _session_total_cost. _bank_link_spend reads the cost ONCE at teardown, so
    banking that counter would record only the LAST section.

    Magnitude, from the shipped kits: 8 sections (W-7), 13 (f1040), 27 (i-90)
    -- so 88% to 96% of a client's real spend was discarded, and a $10 ceiling
    would have behaved like $80-$250 while LOOKING enforced. That is worse
    than no ceiling, because it reports success.

    session_cost_usd() must therefore read the counter that SURVIVES the
    switch. Asserted on the real class, not a double.
    """
    from backend.adapters.live_ai_gemini import LiveAIGemini

    ai = LiveAIGemini.__new__(LiveAIGemini)      # no network, no config
    ai._session_total_cost = 0.0
    ai._connection_total_cost = 0.0

    # Section 1 costs $2.
    ai._session_total_cost += 2.0
    ai._connection_total_cost += 2.0
    assert ai.session_cost_usd() == pytest.approx(2.0)

    # SECTION SWITCH: _run_session_loop zeroes the per-session counter.
    ai._session_total_cost = 0.0

    # Section 2 costs $1.50.
    ai._session_total_cost += 1.5
    ai._connection_total_cost += 1.5

    # The ceiling must see $3.50, not $1.50.
    assert ai.session_cost_usd() == pytest.approx(3.5), (
        "a section switch discarded earlier spend -- the ceiling would bank "
        "only the last section of an 8-to-27 section form"
    )


def test_session_cost_usd_does_not_read_the_RESET_counter():
    """Guards the specific regression: reading _session_total_cost again.

    Derived from the shipped source, because the mistake is a one-token edit
    and every other test would stay green.
    """
    import inspect

    from backend.adapters.live_ai_gemini import LiveAIGemini

    body = inspect.getsource(LiveAIGemini.session_cost_usd)
    assert "_connection_total_cost" in body
    assert "return float(self._session_total_cost)" not in body, (
        "session_cost_usd reads the per-SESSION counter, which a section "
        "switch resets -- see test_the_cost_counter_SURVIVES_a_section_switch"
    )


def test_each_connection_gets_its_OWN_adapter_instance():
    """The ceiling's per-connection counter assumes a FRESH adapter.

    _connection_total_cost is never reset, so if one LiveAIGemini instance
    were shared across two WebSocket connections, a second client would
    inherit the first client's spend and be refused for someone else's usage.

    get_live_ai already returns a fresh instance per call -- dependencies.py
    documents a PAST bug where FastAPI's dependency caching shared one adapter
    and crossed the callbacks. That property is now load-bearing for billing
    too, so pin it: an lru_cache added to get_live_ai here would silently
    charge clients for each other.
    """
    import inspect

    from backend import dependencies

    src = inspect.getsource(dependencies.get_live_ai)
    assert "lru_cache" not in src and "@cache" not in src, (
        "get_live_ai is cached -- one adapter would be shared across "
        "connections and the spend ceiling would charge a client for "
        "someone else's session"
    )

    a = dependencies.get_live_ai.__wrapped__ if hasattr(
        dependencies.get_live_ai, "__wrapped__") else dependencies.get_live_ai
    assert a is dependencies.get_live_ai, "get_live_ai is wrapped by a cache"


def test_the_two_cost_counters_ACCRUE_IN_LOCKSTEP():
    """Both counters must be fed at every accrual site.

    THE REGRESSION THIS CATCHES, and it is worse than the bug it follows:
    delete the _connection_total_cost accrual and session_cost_usd() returns
    0.0 forever, so _bank_link_spend banks NOTHING and the ceiling never
    accumulates at all -- while the per-session cost log looks completely
    normal. Verified unpinned before this test existed: deleting that line
    left 42 tests green across test_link_spend and test_websocket_ephemeral.

    Derived from the shipped source rather than exercised, because the accrual
    sits deep inside the live receive loop -- driving it needs a real Gemini
    stream, and a test that heavy would pin the harness rather than the
    property. What must hold is a LOCKSTEP invariant: every site that adds to
    the per-session counter adds the same value to the per-connection one.
    """
    import inspect
    import re

    from backend.adapters import live_ai_gemini

    src = inspect.getsource(live_ai_gemini)

    session_sites = re.findall(r"_session_total_cost\s*\+=\s*(\w+)", src)
    connection_sites = re.findall(r"_connection_total_cost\s*\+=\s*(\w+)", src)

    assert session_sites, "no accrual site found -- did the counter move?"
    assert session_sites == connection_sites, (
        "the two cost counters no longer accrue in lockstep: "
        f"_session_total_cost += {session_sites} but "
        f"_connection_total_cost += {connection_sites}. "
        "If the per-connection accrual is missing, the spend ceiling banks "
        "NOTHING and never fires; if it is fed a different value, the "
        "ceiling and the cost log disagree."
    )
