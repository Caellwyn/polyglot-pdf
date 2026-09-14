"""backend/services/plans.py -- the firm plan schema (tier + monthly_credits
+ rollover) and its validation (bd polyglot-pdf-0euzk).

ASCII only.
"""
import pytest

from backend.services import plans


def test_default_plan_is_the_maintainers_starting_numbers():
    """The 2026-09-14 pricing decision, verbatim: starter tier, 35
    credits/month, no rollover.

    Mutation: change any one of the three values -- red."""
    assert plans.DEFAULT_PLAN == {
        "tier": "starter", "monthly_credits": 35, "rollover": False,
    }


def test_default_plan_is_a_valid_plan():
    """The default itself must pass its own validator -- a default that
    fails validate_plan would mean backfill_firm_kind.py writes a plan no
    other route could ever accept.

    Mutation: change DEFAULT_PLAN's tier to something outside PLAN_TIERS --
    red."""
    plans.validate_plan(plans.DEFAULT_PLAN)  # must not raise


def test_starter_is_the_only_declared_tier():
    """PLAN_TIERS is a closed list; today it holds exactly one tier.

    Mutation: add a second tier without updating this test -- red (this test
    exists so a tier addition is deliberate, never accidental)."""
    assert plans.PLAN_TIERS == ("starter",)


@pytest.mark.parametrize("tier", ["starter"])
def test_validate_plan_accepts_every_declared_tier(tier):
    """Derived from PLAN_TIERS (scar #8: pin the set, not one instance) --
    a tier added to the tuple without a working validate_plan path fails
    here.

    Mutation: make validate_plan reject `tier` outright -- red."""
    plans.validate_plan(
        {"tier": tier, "monthly_credits": 10, "rollover": False})


@pytest.mark.parametrize("bad_tier", ["gold", "STARTER", "", "premium", None])
def test_validate_plan_refuses_an_unknown_tier(bad_tier):
    """Mutation: drop the `tier not in PLAN_TIERS` check -- every
    parametrization goes red. Verified per parametrization."""
    with pytest.raises(ValueError, match="tier"):
        plans.validate_plan(
            {"tier": bad_tier, "monthly_credits": 10, "rollover": False})


@pytest.mark.parametrize("bad_credits", [0, -1, -35])
def test_validate_plan_refuses_a_non_positive_monthly_credits(bad_credits):
    """Mutation: drop the `monthly_credits <= 0` check -- every
    parametrization goes red. Verified per parametrization."""
    with pytest.raises(ValueError, match="monthly_credits"):
        plans.validate_plan(
            {"tier": "starter", "monthly_credits": bad_credits,
             "rollover": False})


@pytest.mark.parametrize("bad_credits", ["35", 35.0, True, None, [35]])
def test_validate_plan_refuses_a_non_int_monthly_credits(bad_credits):
    """A string, float, bool or list must not silently coerce -- the same
    non-numeric-input trap credit_ledger.py's usd_amount checks guard
    against (a bool is an int subclass, so it needs its own explicit
    exclusion). Mutation: drop the isinstance/bool guard -- every
    parametrization goes red. Verified per parametrization."""
    with pytest.raises(ValueError, match="monthly_credits"):
        plans.validate_plan(
            {"tier": "starter", "monthly_credits": bad_credits,
             "rollover": False})


@pytest.mark.parametrize("bad_rollover", ["true", 1, 0, None, "False"])
def test_validate_plan_refuses_a_non_bool_rollover(bad_rollover):
    """Mutation: drop the isinstance(rollover, bool) check -- every
    parametrization goes red. Verified per parametrization."""
    with pytest.raises(ValueError, match="rollover"):
        plans.validate_plan(
            {"tier": "starter", "monthly_credits": 10,
             "rollover": bad_rollover})


def test_validate_plan_refuses_a_non_dict():
    """Mutation: drop the `isinstance(plan, dict)` guard -- this goes red
    (a bare string would otherwise reach plan.get and raise AttributeError,
    not the clean ValueError every other caller catches)."""
    with pytest.raises(ValueError, match="dict"):
        plans.validate_plan("not-a-dict")


def test_validate_plan_accepts_rollover_true():
    """The accumulating-allotment mode must validate too, not just the
    default False -- guards against a stray `is False` check in
    validate_plan that would refuse a legitimate True.

    Mutation: change `isinstance(rollover, bool)` to `rollover is False` --
    red."""
    plans.validate_plan(
        {"tier": "starter", "monthly_credits": 35, "rollover": True})
