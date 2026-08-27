"""Accumulated AI spend per client link, and the ceiling that stops it.

bd polyglot-pdf-ik7e. `link_budget.py` answers "what is the limit?"; this module
answers "how much has this link spent, and is it over?".

WHY THE SPEND LIVES NEXT TO THE REDEMPTION RECORD. Both are per-jti facts about
one link, both must survive a reconnect, and both are already fail-closed. The
spend fields are written onto the SAME `link_redemptions/{jti}` document rather
than a parallel collection, so a link is one document and the two cannot drift
apart.

THE KEY IS THE jti, AND THAT IS THE WHOLE POINT (see the bead's implementation
note). The bead originally named `form_session_id`. That value survives
reconnects, but it is generated IN THE BROWSER
(frontend/src/schema-forms/state/schemaFormState.ts, `fss_<timestamp>_<random>`)
and lives in sessionStorage -- so a client who wants more free AI time clears
storage and gets a fresh budget. A ceiling keyed on it is defeated by a page
refresh. The `jti` comes from the token WE signed and cannot be forged or reset
by its holder. This is the same rule already load-bearing across the client-link
work: trust what we signed, never what the caller hands us.

SCOPE: CLIENT LINKS ONLY. A staff session has no jti. Staff are authenticated
employees, not the abuse surface this defends against, and a ceiling that cuts
off a paralegal mid-form would create a support problem while protecting
nothing. Staff are exempt EXPLICITLY here rather than by accident.

WHAT A BREACH DOES (maintainer, 2026-08-27): stop the VOICE session, keep
everything else. The client's answers live client-side, and retrieval never
redeems, so their download, print and preview keep working and they can finish
the remaining fields by typing. A ceiling hit must never look like the product
breaking.

FAIL-CLOSED, WITH ONE DELIBERATE ASYMMETRY. An unreachable store REFUSES a new
session (same polarity as the redemption gate -- an unbounded paid session is
the thing we are preventing). But a failed WRITE of an increment does NOT kill
a session already in flight: the spend is already incurred, the client is
mid-sentence, and dropping them for a bookkeeping error costs a real person
their work to protect a number we can reconcile from the token logs. The next
`check` still refuses, so the ceiling holds within one session's worth of
overrun.
"""

from __future__ import annotations

import time
from typing import Optional

import structlog

from backend.services.link_budget import cost_ceiling_usd_for_kit
# _collection and _enabled are underscore-private to link_redemptions, and
# reaching for them is DELIBERATE rather than lazy: the spend fields live on
# that module's own documents, so re-deriving the collection handle here would
# mean two places that must agree on which collection a link lives in. Sharing
# the accessor is what guarantees they cannot drift. Pinned by a test that
# fails if either name disappears.
from backend.services.link_redemptions import (  # noqa: PLC2701
    RedemptionUnavailable,
    _collection,
    _enabled,
)

_log = structlog.get_logger(__name__)

# Field names on the link_redemptions/{jti} document.
SPEND_FIELD = "spend_usd"
TURNS_FIELD = "turns"


class LinkBudgetExhausted(Exception):
    """This link has spent its ceiling. Refuse new PAID work, keep retrieval."""


def _ceiling_for(kit_metadata: Optional[dict]) -> float:
    return cost_ceiling_usd_for_kit(kit_metadata)


def spend_so_far(jti: str) -> float:
    """USD already spent on this link, across every session and reconnect.

    Raises RedemptionUnavailable when the store cannot answer -- the caller
    must then refuse, because "we cannot tell how much this link has spent" and
    "this link has spent nothing" must never be the same answer.
    """
    if not _enabled():
        raise RedemptionUnavailable("redemption store is not enabled")
    try:
        snap = _collection().document(jti).get()
    except Exception as exc:  # noqa: BLE001 -- any store failure refuses
        _log.error("link_spend_read_failed", jti=jti, error=str(exc))
        raise RedemptionUnavailable(str(exc)) from exc
    if not snap.exists:
        return 0.0
    rec = snap.to_dict() or {}
    raw = rec.get(SPEND_FIELD)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.0
    return float(raw) if raw > 0 else 0.0


def check_budget(jti: str, kit_metadata: Optional[dict] = None) -> float:
    """Raise LinkBudgetExhausted if this link is at or over its ceiling.

    Returns the remaining USD when there is room. Call this BEFORE starting a
    paid session, not after -- the point is to refuse the session, not to
    discover afterwards that it should have been refused.
    """
    ceiling = _ceiling_for(kit_metadata)
    spent = spend_so_far(jti)
    if spent >= ceiling:
        _log.warning(
            "link_budget_exhausted",
            jti=jti,
            spend_usd=round(spent, 6),
            ceiling_usd=ceiling,
        )
        raise LinkBudgetExhausted(
            f"link has spent {spent:.4f} of its {ceiling:.2f} ceiling"
        )
    return ceiling - spent


def record_spend(
    jti: str,
    cost_usd: float,
    turns: int = 0,
    now: Optional[float] = None,
) -> None:
    """Add this session's spend to the link's running total.

    Best-effort BY DESIGN: a store failure here is logged and swallowed rather
    than raised. See the module docstring -- the spend is already incurred and
    the client is mid-form; the next check_budget still refuses.

    `turns` is carried as a DIAGNOSTIC, never as a limit (maintainer, 2026-08-24:
    cost is the enforcement unit, turns explain WHY a session was expensive). A
    client looping on question 12 and a client answering 100 questions with long
    responses can produce the same cost with completely different causes, and
    the turns/question ratio is also how a model regression surfaces.
    """
    if not jti or cost_usd <= 0:
        return
    if not _enabled():
        return
    try:
        # firebase_admin's firestore, NOT google.cloud.firestore directly:
        # get_db() returns a firebase_admin client, and this repo has exactly
        # one Firestore SDK path. Both expose Increment; using the one the
        # rest of the backend already imports keeps it that way.
        from firebase_admin import firestore

        updates = {
            SPEND_FIELD: firestore.Increment(float(cost_usd)),
            "spend_updated_at": int(now if now is not None else time.time()),
        }
        if turns > 0:
            updates[TURNS_FIELD] = firestore.Increment(int(turns))
        _collection().document(jti).update(updates)
    except Exception as exc:  # noqa: BLE001 -- never kill a live session
        _log.error(
            "link_spend_write_failed",
            jti=jti,
            cost_usd=round(cost_usd, 6),
            error=str(exc),
        )
