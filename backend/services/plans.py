"""The firm plan: tier + monthly credit allotment + rollover (bd
polyglot-pdf-0euzk, Epic 2 follow-up).

WHY THIS EXISTS. The maintainer's 2026-09-14 pricing decision: "35 credits
per month cap as a starting place; leave room for tiered subscription levels
with different allotments, and pay-as-you-go or overage later." Modeling
that as DATA on the firm (a `plan` dict) plus one scheduled top-up
(admin_backend/routes/credit_routes.py::run_monthly_topup) means a second
tier and eventually pay-as-you-go/overage are new ROWS -- a new tier name in
PLAN_TIERS, a different monthly_credits value on a firm's plan doc -- rather
than new CODE PATHS. This module is the ONE place PLAN_TIERS is declared and
the one place a plan dict is validated, so a tier check anywhere else (the
admin route, a future console picker) reads this list rather than growing
its own copy.

Doc shape (a sub-object on `firms/{firm_id}.plan`):
    tier: str              one of PLAN_TIERS (closed list; today: "starter")
    monthly_credits: int   positive; the monthly top-up target/increment
    rollover: bool         True (default, bd polyglot-pdf-hnlj3, maintainer
                            decision 2026-09-15: "credits roll over -- no
                            real reason not to"): the top-up ADDS
                            monthly_credits on top of whatever is left (an
                            accumulating allotment). False: the top-up
                            brings the balance up TO monthly_credits (a
                            "use it or lose it" cap) -- still a valid,
                            settable value (PATCH /admin/firms/{id}/plan),
                            just no longer what a NEW or backfilled firm
                            gets by default.

DEFAULT_PLAN is the shape scripts/backfill_firm_kind.py's plan backfill and
admin_backend/routes/firm_routes.py's create route both apply to a firm with
no stored `plan` -- {tier: "starter", monthly_credits: 35, rollover: True},
the maintainer's own starting numbers (rollover flipped True by bd
polyglot-pdf-hnlj3, 2026-09-15 -- see that bead for the "35 credits per
month cap" wording correction this implies: with rollover the default,
"cap" is the wrong word for what monthly_credits now normally means. The
one existing firm (staging-mock) was switched to rollover by hand the same
day, ahead of this code change, so DEFAULT_PLAN and live data agree). It is
a plain dict literal (not a function) so every caller sees the IDENTICAL
default object shape; callers that mutate it must copy first
(`dict(DEFAULT_PLAN)`), since a shared mutable default is exactly the
aliasing bug this module's simplicity should not invite.

PLAN_TIERS IS CLOSED, ON PURPOSE. A firm's tier gates NOTHING behavioral
today (there is only one tier) -- it exists so a second tier is a one-line
addition to this tuple plus a maintainer-approved monthly_credits value, not
a schema migration. validate_plan() refuses any tier not in this list with a
ValueError the admin route translates to a 422, exactly the same shape
backend/services/firms.py's FIRM_KIND_MOCK/LIVE closed-list check and
admin_backend/routes/firm_routes.py's _FIRM_KINDS validation already use.

NO OVERAGE / PAY-AS-YOU-GO YET (deliberately deferred to Epic 5's Stripe
work). The reserved ledger entry type living in
backend/services/credit_ledger.py::TYPE_OVERAGE_PURCHASE (a constant with NO
writer) is the seam: Epic 5 adds the writer without this module's schema, or
PLAN_TIERS, needing to change at all.

ASCII only.
"""
from __future__ import annotations

from typing import Any

# The closed list of plan tiers. Today: exactly one. A future tier is a new
# string here plus its own monthly_credits value chosen by the maintainer --
# never a code path change on any caller that already validates against this
# list (validate_plan below, and any console picker built later).
PLAN_TIERS = ("starter",)

# The maintainer's 2026-09-14 starting numbers (rollover flipped to True by
# bd polyglot-pdf-hnlj3, 2026-09-15: "credits roll over -- no real reason
# not to"), applied by scripts/backfill_firm_kind.py (only when a firm has
# no stored `plan`) and by admin_backend/routes/firm_routes.py's create
# route (every new firm). A plain dict literal: copy it
# (dict(DEFAULT_PLAN)) before mutating, never mutate this module-level
# object in place.
DEFAULT_PLAN: dict[str, Any] = {
    "tier": "starter",
    "monthly_credits": 35,
    "rollover": True,
}


def validate_plan(plan: dict) -> None:
    """Refuse a malformed plan dict BEFORE it is written anywhere.

    Checks ONLY the three fields the doc shape declares -- `tier` a member
    of PLAN_TIERS, `monthly_credits` a positive int, `rollover` a bool --
    mirroring credit_ledger._validate's own "refuse before opening a
    transaction" shape. Raises ValueError (never a Firestore-specific
    exception, so both the admin route and a plain CLI can catch the same
    type and translate it to their own error surface -- the route to 422,
    a script to a printed refusal).
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be a dict, got {!r}".format(plan))
    tier = plan.get("tier")
    if tier not in PLAN_TIERS:
        raise ValueError(
            "tier must be one of {}, got {!r}".format(PLAN_TIERS, tier)
        )
    monthly_credits = plan.get("monthly_credits")
    if not isinstance(monthly_credits, int) or isinstance(
            monthly_credits, bool) or monthly_credits <= 0:
        raise ValueError(
            "monthly_credits must be a positive int, got {!r}".format(
                monthly_credits)
        )
    rollover = plan.get("rollover")
    if not isinstance(rollover, bool):
        raise ValueError(
            "rollover must be a bool, got {!r}".format(rollover)
        )
