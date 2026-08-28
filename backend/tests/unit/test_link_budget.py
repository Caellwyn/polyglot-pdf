"""The tunable link caps (bd polyglot-pdf-ik7e).

These pin POLICY, and the property that matters most is not "the default is 30".
It is that a MALFORMED override never removes a cap. A spend ceiling that
silently becomes unlimited because someone typed `LINK_COST_CEILING_USD=ten` is
worse than no ceiling at all, because it LOOKS enforced.
"""

import pytest

from backend.services import link_budget


# ---------------------------------------------------------------------------
# Defaults (maintainer, 2026-08-27)
# ---------------------------------------------------------------------------


def test_the_shipped_defaults_are_the_maintainers_numbers(monkeypatch):
    """30 links per firm, $10 per link. Pinned so a later edit is deliberate."""
    monkeypatch.delenv("LINK_FIRM_CAP", raising=False)
    monkeypatch.delenv("LINK_COST_CEILING_USD", raising=False)
    assert link_budget.firm_link_cap() == 30
    assert link_budget.default_cost_ceiling_usd() == 10.0


def test_both_caps_are_tunable_without_a_code_change(monkeypatch):
    """The whole point of the module: an env var retunes a live deployment."""
    monkeypatch.setenv("LINK_FIRM_CAP", "75")
    monkeypatch.setenv("LINK_COST_CEILING_USD", "25.50")
    assert link_budget.firm_link_cap() == 75
    assert link_budget.default_cost_ceiling_usd() == 25.50


def test_the_env_is_read_at_CALL_time_not_import_time(monkeypatch):
    """Captured-at-import config cannot be retuned without a redeploy.

    This is the property that makes the value operationally tunable, and it is
    invisible in a test that only ever reads the value once.
    """
    monkeypatch.setenv("LINK_COST_CEILING_USD", "5")
    assert link_budget.default_cost_ceiling_usd() == 5.0
    monkeypatch.setenv("LINK_COST_CEILING_USD", "50")
    assert link_budget.default_cost_ceiling_usd() == 50.0


# ---------------------------------------------------------------------------
# A bad override must never REMOVE the cap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["", "ten", "abc", "10abc", "  ", "None", "null", "-5", "0", "nan", "inf"],
)
def test_a_MALFORMED_cost_override_falls_back_rather_than_uncapping(monkeypatch, bad):
    """Every unusable value yields the DEFAULT, never unlimited.

    `0` and negatives are included deliberately: read literally `0` means "no
    spend at all", but as a typo it far more likely means "unset", and guessing
    wrong there breaks every client session.
    """
    monkeypatch.setenv("LINK_COST_CEILING_USD", bad)
    assert link_budget.default_cost_ceiling_usd() == 10.0


@pytest.mark.parametrize("bad", ["", "thirty", "-1", "0", "3.7.1", "  "])
def test_a_MALFORMED_firm_cap_falls_back_rather_than_uncapping(monkeypatch, bad):
    monkeypatch.setenv("LINK_FIRM_CAP", bad)
    assert link_budget.firm_link_cap() == 30


# ---------------------------------------------------------------------------
# Per-form ceilings -- the room the maintainer asked for
# ---------------------------------------------------------------------------


def test_a_kit_can_carry_its_OWN_ceiling(monkeypatch):
    """Per-form pricing: a $5 form and a $15 form under one firm."""
    monkeypatch.delenv("LINK_COST_CEILING_USD", raising=False)
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
def test_a_kit_WITHOUT_a_usable_ceiling_gets_the_global_default(monkeypatch, meta):
    """A malformed kit override must not uncap that ONE form.

    `True` is in this list on purpose: bool subclasses int in Python, so a
    `true` in metadata.json would otherwise resolve to a $1 ceiling.
    """
    monkeypatch.delenv("LINK_COST_CEILING_USD", raising=False)
    assert link_budget.cost_ceiling_usd_for_kit(meta) == 10.0


def test_a_BOOLEAN_kit_value_does_not_become_a_ONE_DOLLAR_ceiling(monkeypatch):
    """bool subclasses int, so `true` in metadata.json floats to 1.0.

    Without an explicit carve-out that resolves to a $1.00 ceiling -- a form
    silently capped at a fifth of a normal session, which reads as "the AI
    stops working on this form" rather than as a config error. Its own test
    because inside the malformed-values parametrization it stayed GREEN when
    the carve-out was deleted: the other cases in that list fail for different
    reasons and masked it.
    """
    monkeypatch.delenv("LINK_COST_CEILING_USD", raising=False)
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": True}) == 10.0
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": False}) == 10.0


def test_a_kit_ceiling_beats_the_env_default(monkeypatch):
    """Precedence: the FORM's number wins where it has one."""
    monkeypatch.setenv("LINK_COST_CEILING_USD", "20")
    assert link_budget.cost_ceiling_usd_for_kit({"link_cost_ceiling_usd": 5}) == 5.0
    # ...and a kit with no opinion still follows the retuned global
    assert link_budget.cost_ceiling_usd_for_kit({}) == 20.0
