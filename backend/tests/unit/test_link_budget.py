"""The tunable link caps (bd polyglot-pdf-ik7e; moved to runtime_config by
bd polyglot-pdf-bg313).

These pin POLICY, and the property that matters most is not "the default is 30".
It is that a MALFORMED override never removes a cap. A spend ceiling that
silently becomes unlimited because someone typed `LINK_COST_CEILING_USD=ten` is
worse than no ceiling at all, because it LOOKS enforced.

firm_link_cap() and default_cost_ceiling_usd() now resolve through
backend.services.runtime_config rather than os.getenv directly (bd
polyglot-pdf-bg313) -- runtime_config's OWN malformed-value and call-time
coverage lives in test_runtime_config.py. What stays here: the two global
resolvers still delegate correctly, and the per-kit override
(cost_ceiling_usd_for_kit) -- which never touched env and is unaffected by
the move.
"""

import pytest

from backend.services import link_budget, runtime_config


@pytest.fixture(autouse=True)
def _clear_runtime_config_cache():
    """runtime_config caches per-channel state at module scope; a value one
    test patches must not leak into the next."""
    runtime_config.clear_cache()
    yield
    runtime_config.clear_cache()


# ---------------------------------------------------------------------------
# Defaults (maintainer, 2026-08-27)
# ---------------------------------------------------------------------------


def test_the_shipped_defaults_are_the_maintainers_numbers(monkeypatch):
    """30 links per firm, $10 per link, when runtime_config has nothing
    stored (no Firestore access in this test process -> env default)."""
    assert link_budget.firm_link_cap() == 30
    assert link_budget.default_cost_ceiling_usd() == 10.0


def test_both_caps_are_tunable_without_a_code_change(monkeypatch):
    """The whole point of the module: retuning without a code change.
    Delegated to runtime_config now, so the tunable surface is a resolver
    patch rather than an env var -- see test_runtime_config.py for the
    Firestore-level tunability this stands on.

    Patched at link_budget's OWN bound name (`_rc_link_firm_cap`, imported
    `from ... import ... as`), not at runtime_config's module attribute --
    link_budget holds its own reference to the function object, so patching
    runtime_config.link_firm_cap after that import would silently miss it.
    """
    monkeypatch.setattr(link_budget, "_rc_link_firm_cap", lambda: 75)
    monkeypatch.setattr(link_budget, "_rc_link_cost_ceiling_usd", lambda: 25.50)
    assert link_budget.firm_link_cap() == 75
    assert link_budget.default_cost_ceiling_usd() == 25.50


def test_link_budget_calls_runtime_config_at_CALL_time_not_import_time(monkeypatch):
    """Captured-at-import config cannot be retuned without a redeploy.

    This is the property that makes the value operationally tunable, and it is
    invisible in a test that only ever reads the value once.
    """
    monkeypatch.setattr(link_budget, "_rc_link_cost_ceiling_usd", lambda: 5.0)
    assert link_budget.default_cost_ceiling_usd() == 5.0
    monkeypatch.setattr(link_budget, "_rc_link_cost_ceiling_usd", lambda: 50.0)
    assert link_budget.default_cost_ceiling_usd() == 50.0


# ---------------------------------------------------------------------------
# Per-form ceilings -- the room the maintainer asked for. UNAFFECTED by the
# runtime_config move: cost_ceiling_usd_for_kit never read env directly, only
# default_cost_ceiling_usd()'s fallback.
# ---------------------------------------------------------------------------


def test_a_kit_can_carry_its_OWN_ceiling():
    """Per-form pricing: a $5 form and a $15 form under one firm."""
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": 5}) == 5.0
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": 15.0}) == 15.0
    # a string survives the JSON round-trip a console edit would produce
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": "7.25"}) == 7.25


@pytest.mark.parametrize(
    "meta",
    [
        None,
        {},
        {"other_key": 3},
        "not-a-dict",
        {"link_cost_ceiling_usd": None},
        {"link_cost_ceiling_usd": "free"},
        {"link_cost_ceiling_usd": -4},
        {"link_cost_ceiling_usd": 0},
        {"link_cost_ceiling_usd": True},
        {"link_cost_ceiling_usd": []},
    ],
)
def test_a_kit_WITHOUT_a_usable_ceiling_gets_the_global_default(meta):
    """A malformed kit override must not uncap that ONE form.

    `True` is in this list on purpose: bool subclasses int in Python, so a
    `true` in metadata.json would otherwise resolve to a $1 ceiling.
    """
    assert link_budget.cost_ceiling_usd_for_kit(meta) == 10.0


def test_a_BOOLEAN_kit_value_does_not_become_a_ONE_DOLLAR_ceiling():
    """bool subclasses int, so `true` in metadata.json floats to 1.0.

    Without an explicit carve-out that resolves to a $1.00 ceiling -- a form
    silently capped at a fifth of a normal session, which reads as "the AI
    stops working on this form" rather than as a config error. Its own test
    because inside the malformed-values parametrization it stayed GREEN when
    the carve-out was deleted: the other cases in that list fail for different
    reasons and masked it.
    """
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": True}) == 10.0
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": False}) == 10.0


def test_a_kit_ceiling_beats_the_global_default(monkeypatch):
    """Precedence: the FORM's number wins where it has one."""
    monkeypatch.setattr(link_budget, "_rc_link_cost_ceiling_usd", lambda: 20.0)
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": 5}) == 5.0
    # ...and a kit with no opinion still follows the retuned global
    assert link_budget.cost_ceiling_usd_for_kit({}) == 20.0


# ---------------------------------------------------------------------------
# Per-link cap FROM THE TOKEN (bd polyglot-pdf-ah5d3 / A4, closing 4tjt7).
# Precedence at the socket: token cap_usd > global ceiling, and NOTHING else
# -- no per-connect kit read. Same defensive parsing as cost_ceiling_usd_for_kit
# above, funnelled through the same _positive_float helper.
# ---------------------------------------------------------------------------


def test_a_token_WITH_a_cap_overrides_the_global():
    """The precedence this bead exists to add: the socket honours the link's
    OWN ceiling, resolved once at mint, not the global."""
    assert link_budget.cost_ceiling_usd_for_claims({"cap_usd": 3.0}) == 3.0
    assert link_budget.cost_ceiling_usd_for_claims({"cap_usd": 15}) == 15.0


def test_a_token_WITHOUT_a_cap_uses_the_global():
    """A token minted before A3 wires cap_usd through, or for a kit with no
    resolvable ceiling, carries no claim -- and must fall through exactly
    like a kit with no per-form opinion does."""
    assert link_budget.cost_ceiling_usd_for_claims({}) == 10.0
    assert link_budget.cost_ceiling_usd_for_claims(None) == 10.0
    assert link_budget.cost_ceiling_usd_for_claims({"firm_id": "f1"}) == 10.0


@pytest.mark.parametrize(
    "claims",
    [
        None,
        {},
        {"other_key": 3},
        "not-a-dict",
        {"cap_usd": None},
        {"cap_usd": "free"},
        {"cap_usd": -4},
        {"cap_usd": 0},
        {"cap_usd": True},
        {"cap_usd": []},
    ],
)
def test_a_MALFORMED_cap_usd_claim_falls_through_to_the_global(claims):
    """The property that matters most: a bad claim must never read as
    unlimited spend. Mirrors cost_ceiling_usd_for_kit's own malformed-value
    parametrization -- this is the same defensive-parsing rule applied to a
    different source dict."""
    assert link_budget.cost_ceiling_usd_for_claims(claims) == 10.0


def test_a_BOOLEAN_cap_usd_claim_does_not_become_a_ONE_DOLLAR_ceiling():
    """bool subclasses int, so a stray `True` would otherwise resolve to a
    $1.00 ceiling -- link_tokens.mint_link_token already refuses to sign a
    bool in, but this function does not trust that alone."""
    assert link_budget.cost_ceiling_usd_for_claims({"cap_usd": True}) == 10.0
    assert link_budget.cost_ceiling_usd_for_claims({"cap_usd": False}) == 10.0


def test_a_token_cap_beats_a_RETUNED_global(monkeypatch):
    """Precedence holds even when the global itself has been retuned -- the
    token's number is not "the default at mint time", it wins outright."""
    monkeypatch.setattr(link_budget, "_rc_link_cost_ceiling_usd", lambda: 20.0)
    assert link_budget.cost_ceiling_usd_for_claims({"cap_usd": 3.0}) == 3.0
    assert link_budget.cost_ceiling_usd_for_claims({}) == 20.0


def test_a_cap_usd_string_survives_a_JSON_round_trip():
    """A claims dict decoded from JSON (verify_link_token's json.loads) can
    hand back either an int/float or -- if some future caller stringifies --
    a numeric string; both must resolve the same way as the per-kit override
    does."""
    assert link_budget.cost_ceiling_usd_for_claims({"cap_usd": "7.25"}) == 7.25
