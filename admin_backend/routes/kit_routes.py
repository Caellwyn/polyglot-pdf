"""Kit commercial settings on the admin service (bd polyglot-pdf-f0kuu,
Epic 2 Track B bead B3).

TWO ROUTES:

    GET /admin/kits                          every kit, priced or defaulted
    GET /admin/kits/{kit_id}/commercial       one kit's resolved commercial
    PUT /admin/kits/{kit_id}/commercial       set credit_cost/burn_cap_usd/display

ALL THREE behind require_app_admin -- kit pricing is an operator-only
concern, with no firm-manager counterpart (unlike the link-listing routes).

READ SIDE REUSES backend/services/kit_commercials.py::resolve_commercial,
THE SAME READER bead A3's mint transaction calls. This module does not add
a second reader: the plan is explicit ("do not write a second reader"), and
test_get_commercial_calls_the_shared_a3_reader below asserts the import by
name rather than merely by behavior, so a future rewrite that inlines a
second copy of the fallback logic is caught even if it happens to compute
the same numbers today. Both GET routes below spread that reader's return
dict directly, so `display` (bd polyglot-pdf-zcbm1: resolve_commercial now
returns the kit's stored display map, or {} when there is none) reaches the
console for free -- no route change was needed here for that bead, only
the reader itself.

WRITE SIDE VALIDATES BEFORE ANY WRITE (exit criterion 1): credit_cost must
be a positive int (bool excluded -- bool is an int subclass, so a stray
`true` would otherwise silently price a form at 1 credit), burn_cap_usd must
be a positive finite float (NaN and +-inf refused), display must be a
dict of strings if present at all. This is deliberately STRICTER than the
read side's defensive fallback (kit_commercials.resolve_commercial and
link_budget.cost_ceiling_usd_for_kit fall back to a default on a bad stored
value so an old bad edit can never remove a form's ceiling) -- the WRITE
path's job is different: refuse the bad edit outright so it never reaches
the store as a "successful" write that the read side then silently
overrides. Mirrors link_budget.py's polarity (zero/negative/NaN/inf/bool
all refused) without importing its module-private helpers, which are typed
for str input read from an env var, not a JSON request body.

FIELD NAME: the request body and the stored doc both spell the ceiling
"burn_cap_usd" (the storage key); resolve_commercial's own vocabulary
spells the resolved value "cap_usd" (bead A3, unchanged here -- the plan
says not to write a second reader, so this module does not rename it).
The PUT response therefore echoes the value under BOTH "burn_cap_usd"
(matching its own request body) and "cap_usd" (matching what GET returns
for the same kit) so a console reading either route's response after a
write does not need a per-route translation for one number.

AUDITED IN-TRANSACTION (exit criterion 1): the write and its audit row
share one Firestore transaction, mirroring config_routes.py's
_apply_config_write / firm_routes.py's _apply_firm_patch shape -- read
(before), write, audit, all inside one @firestore.transactional body, so a
forced audit failure leaves the commercial doc unchanged.

GET /admin/kits LISTS EVERY KIT IN THE FORM-KIT STORE (bd polyglot-pdf-f0kuu,
plan: "backend/services/form_kits.py list"), joining each kit_id with its
resolved commercial doc (or the global defaults) via the SAME
resolve_commercial reader -- so the console's kit list and the mint path
can never disagree about what a kit costs. list_kit_ids() is ASYNC (the
form-kit store may be a GCS-backed one), unlike every other Firestore-only
helper in this module, so this one route awaits it directly rather than
running it under asyncio.to_thread.

SYNC HELPER, ASYNC ROUTE for the Firestore write/read: matches every other
admin-service call into a synchronous Firestore helper (credit_routes.py's
own docstring; firm_routes.py's asyncio.to_thread precedent).

ASCII only.
"""
from __future__ import annotations

import asyncio
import re
from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import kit_commercials

_log = structlog.get_logger(module="admin_kit_routes")

router = APIRouter()

# The audit `action` string for a kit commercial write. A constant, not an
# inline literal: test_admin_audit_coverage.py and a future console filter
# both key on it.
ACTION_KIT_COMMERCIAL_SET = "kit.commercial.set"

# Same kit-id slug rule as backend/routes/form_kit_routes.py's _KIT_ID_RE
# (bd polyglot-pdf-sbfk) and every other {kit_id} path-segment site in this
# repo, restated here rather than imported for the same reason
# firm_routes.py restates FIRM_ID_RE locally: a cross-module import at
# collection time is more fragile than a literal regex every site agrees on.
# fullmatch, not match: a $-anchored .match still accepts a trailing
# newline, the exact bug class this rule exists to close.
_KIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

_DISPLAY_MAX_KEYS = 20
_DISPLAY_MAX_VALUE_LEN = 500


class KitCommercialPutRequest(BaseModel):
    """credit_cost a positive int, burn_cap_usd a positive finite float,
    display a small string map -- exactly the plan's wording. All three are
    REQUIRED (a PUT replaces the whole commercial doc; a partial update that
    silently kept a stale ceiling from a previous edit is the failure mode
    the per-kit ceiling rule exists to prevent)."""

    credit_cost: Any
    burn_cap_usd: Any
    display: Optional[dict] = None


def _validated_kit_id(kit_id: str) -> str:
    if not kit_id or not _KIT_ID_RE.fullmatch(kit_id):
        raise HTTPException(
            status_code=422,
            detail="kit_id {!r} is not a valid kit id".format(kit_id),
        )
    return kit_id


def _validated_credit_cost(raw: Any) -> int:
    """A positive int, strictly -- refuses rather than falls back (see
    module docstring on why the write side's polarity differs from
    kit_commercials.resolve_commercial's read-side fallback).

    bool excluded explicitly: bool is an int subclass, so an unguarded
    isinstance(raw, int) check would accept `true` as a 1-credit price.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise HTTPException(
            status_code=422,
            detail="credit_cost must be a positive integer, got {!r}".format(
                raw),
        )
    if raw <= 0:
        raise HTTPException(
            status_code=422,
            detail="credit_cost must be a positive integer, got {!r}".format(
                raw),
        )
    return raw


def _validated_burn_cap_usd(raw: Any) -> float:
    """A positive, finite float, strictly. bool excluded for the same
    int-subclass reason as credit_cost; NaN and +-inf refused explicitly
    since `value != value` (NaN) and `value in (inf, -inf)` both parse as
    "numbers" that a naive `> 0` check would let through un-refused on some
    platforms' float formatting."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise HTTPException(
            status_code=422,
            detail="burn_cap_usd must be a positive number, got {!r}".format(
                raw),
        )
    value = float(raw)
    if value != value or value in (float("inf"), float("-inf")) or value <= 0:
        raise HTTPException(
            status_code=422,
            detail="burn_cap_usd must be a positive finite number, "
                   "got {!r}".format(raw),
        )
    return value


def _validated_display(raw: Any) -> dict:
    """A small string map, or absent (defaults to {}). Refuses a non-dict,
    a non-string key/value, or an implausibly large map -- the console label
    is cosmetic, but an unbounded value here is still a write this route
    controls, not free-form storage."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="display must be a map")
    if len(raw) > _DISPLAY_MAX_KEYS:
        raise HTTPException(
            status_code=422,
            detail="display must have at most {} keys".format(
                _DISPLAY_MAX_KEYS),
        )
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise HTTPException(
                status_code=422,
                detail="display keys and values must all be strings",
            )
        if len(value) > _DISPLAY_MAX_VALUE_LEN:
            raise HTTPException(
                status_code=422,
                detail="display.{} exceeds {} characters".format(
                    key, _DISPLAY_MAX_VALUE_LEN),
            )
    return dict(raw)


def _db():
    """The Firestore client, or a 503. Lazy-imported like every other
    Firestore caller in this repo (module import must not require
    firebase_admin to be initialized)."""
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="kit store unavailable")
    return db


def _kit_ref(db, kit_id: str):
    return db.collection(kit_commercials.COLLECTION).document(kit_id)


def _apply_kit_commercial_write(
    *, db, kit_id: str, credit_cost: int, burn_cap_usd: float,
    display: dict, actor: AdminActor, request_id: str,
) -> dict:
    """The commercial write and its audit row, in ONE Firestore transaction
    (exit criterion 1). Mirrors config_routes.py's _apply_config_write /
    firm_routes.py's _apply_firm_patch shape: the @firestore.transactional
    decorator applies INSIDE this function so the module imports with no
    firebase_admin app initialized.

    The BEFORE read lives inside the transaction: Firestore re-runs this
    whole body on contention, and a value read outside would be stale on a
    retry -- the audit row would then record a `before` that was never the
    state the write applied to.
    """
    from firebase_admin import firestore

    kit_ref = _kit_ref(db, kit_id)
    captured: dict[str, Any] = {}

    @firestore.transactional
    def _txn(tx):
        snap = kit_ref.get(transaction=tx)
        before = snap.to_dict() if snap.exists else None
        captured["before"] = before

        after = {
            kit_commercials.CREDIT_COST_KEY: credit_cost,
            kit_commercials.BURN_CAP_USD_KEY: burn_cap_usd,
            "display": display,
            "updated_by": actor.uid,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        tx.set(kit_ref, after)

        # SAME transaction: a failing audit write aborts the commercial
        # write too (exit criterion 1).
        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor.uid,
            actor_email=actor.email,
            action=ACTION_KIT_COMMERCIAL_SET,
            target="kits/{}".format(kit_id),
            before=before,
            after={
                kit_commercials.CREDIT_COST_KEY: credit_cost,
                kit_commercials.BURN_CAP_USD_KEY: burn_cap_usd,
                "display": display,
            },
            request_id=request_id,
        )

    try:
        _txn(db.transaction())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_kit_commercial_write_failed", kit_id=kit_id,
                   error_type=type(exc).__name__)
        raise HTTPException(status_code=500,
                            detail="kit commercial write failed") from exc

    return {"before": captured.get("before")}


@router.get("/admin/kits/{kit_id}/commercial")
async def get_kit_commercial(
    kit_id: str,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """The resolved credit price, USD ceiling, and display label for one
    kit -- the SAME reader bead A3's mint transaction calls (exit criterion
    2), so the console can never show a number the mint path would not also
    use.

    A read, so no audit row. `source` is "kit" when a commercial doc exists,
    "default" when this kit has never been priced -- resolve_commercial's
    own vocabulary, passed straight through. `display` (bd
    polyglot-pdf-zcbm1) is the kit's stored console label map, or {} when
    none is set -- so a console page can read it here and echo it back on a
    PUT instead of always sending {} and silently wiping a seeded label.
    """
    kit_id = _validated_kit_id(kit_id)
    resolved = await asyncio.to_thread(
        kit_commercials.resolve_commercial, kit_id)
    return {"kit_id": kit_id, **resolved}


@router.put("/admin/kits/{kit_id}/commercial")
async def put_kit_commercial(
    kit_id: str,
    body: KitCommercialPutRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Set a kit's commercial doc. Refuses BEFORE any write on a malformed
    credit_cost, burn_cap_usd, or display (422) -- exit criterion 1's other
    half: a bad edit must never remove a form's ceiling, so the value never
    reaches the store as a "successful" write in the first place.
    """
    kit_id = _validated_kit_id(kit_id)
    credit_cost = _validated_credit_cost(body.credit_cost)
    burn_cap_usd = _validated_burn_cap_usd(body.burn_cap_usd)
    display = _validated_display(body.display)

    db = _db()
    request_id = audit_log.new_request_id()
    result = await asyncio.to_thread(
        _apply_kit_commercial_write,
        db=db, kit_id=kit_id, credit_cost=credit_cost,
        burn_cap_usd=burn_cap_usd, display=display, actor=actor,
        request_id=request_id,
    )
    _log.info("admin_kit_commercial_set", kit_id=kit_id,
              credit_cost=credit_cost, burn_cap_usd=burn_cap_usd,
              actor_uid=actor.uid, request_id=request_id)
    return {
        "kit_id": kit_id,
        "credit_cost": credit_cost,
        "burn_cap_usd": burn_cap_usd,
        # Also under resolve_commercial's own key: GET's response (and
        # GET /admin/kits) spreads resolve_commercial's dict, which spells
        # this value "cap_usd" (bead A3's vocabulary, unchanged here). A
        # console screen that both displays a kit's price (GET) and edits
        # it (PUT) needs one key to read for "what did I just set", not a
        # per-route translation for what is the identical stored number --
        # so PUT echoes it under both names rather than only the request
        # body's own field name. Literally the same float just validated
        # and written, not a second read: no way for the two to drift.
        "cap_usd": burn_cap_usd,
        "display": display,
        "before": result["before"],
        "request_id": request_id,
    }


@router.get("/admin/kits")
async def list_kits(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Every kit in the form-kit store, each joined with its resolved
    commercial doc (or the global defaults) via the SAME reader the mint
    path and the single-kit GET above use -- so this list can never disagree
    with what a mint actually charges.

    list_kit_ids() is ASYNC (the store may be GCS-backed), unlike every
    other Firestore call in this module, so it is awaited directly rather
    than run under asyncio.to_thread; resolve_commercial's own Firestore
    read stays under asyncio.to_thread like every other admin-service call
    into a synchronous Firestore helper.

    A read, so no audit row. A store outage (FormKitStoreError -- the exact
    condition that type exists for) is a 502, matching every other
    FormKitStore call site in the repo (see form_kit_routes.py's own
    handling of the same exception), not a bare unhandled 500.
    """
    from backend.services.form_kits import FormKitStoreError, get_form_kit_store

    store = get_form_kit_store()
    try:
        kit_ids = await store.list_kit_ids()
    except FormKitStoreError as exc:
        _log.error("admin_list_kits_failed", error_type=type(exc).__name__)
        raise HTTPException(
            status_code=502, detail="Unable to load form kit list") from exc

    kits = []
    for kit_id in kit_ids:
        resolved = await asyncio.to_thread(
            kit_commercials.resolve_commercial, kit_id)
        kits.append({"kit_id": kit_id, **resolved})
    return {"kits": kits}
