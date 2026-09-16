"""GET/PUT /admin/config/{channel} -- the runtime-config editor (bd
polyglot-pdf-li9x0).

THE FIRST AUDITED MUTATION on the admin service, and the reason the audit
helper ships with a route rather than alone: a helper proven only against a
test double proves nothing about the shape a real route needs.

WHAT IT WRITES. app_config/{channel}, the per-channel Firestore doc
backend/services/runtime_config.py reads (bd polyglot-pdf-bg313, Surface
contract 14). This route is the AUDITED producer that contract names;
scripts/set_runtime_config.py is the un-audited operator CLI that exists to
unblock verification before the console shipped, and it stays as the
documented break-glass path.

THE CHANNEL IS A PATH PARAMETER, not derived from the environment. THE ADMIN
SERVICE HAS NO CHANNEL (admin_backend/main.py): it serves both staging's and
the demo's data, so a channel read off LINK_CHANNEL here would write one
channel's config while the operator believed they were editing the other.
Validated against KNOWN_CHANNELS so a typo creates a config doc no backend
ever reads, silently, instead of failing.

VALIDATION reuses runtime_config's own vocabulary rather than restating it
(CLAUDE.md scar #8 -- one rule, one home):
  - the key must be in runtime_config.RUNTIME_CONFIG_KEYS;
  - the value must survive runtime_config.coerce_value(), the SAME coercion
    a real read applies -- so a value this route accepts cannot silently
    become "malformed" on the next read and fall back to the env default.

THE WRITE AND ITS AUDIT SHARE ONE TRANSACTION. The transaction body reads
the current doc (that read is the audit row's `before`), writes the new
value, and writes the audit row -- all inside one @firestore.transactional
function, so a failing audit write aborts the config write too (exit
criterion 1). Firestore also RETRIES a contended transaction by re-running
the whole body, which is why the before-read lives inside it: a before-value
read outside would go stale on a retry and record a lie.

ASCII only.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from backend.services import runtime_config

_log = structlog.get_logger().bind(module="admin_config_routes")

router = APIRouter()

# The channels that actually exist (docs/doctrine/promotion-tiers.md):
# staging is the disposable test deploy, demo is the protected target shown
# to investors and pilot firms. There is NO prod -- deploy-production.sh
# targets a dead project and refuses to run. Pinned here so a PUT to
# /admin/config/prod 404s instead of creating an orphan doc that looks
# configured and is read by nothing.
KNOWN_CHANNELS = ("demo", "staging")

# The audit `action` string for a config write. A constant rather than an
# inline literal because the coverage test derives the set of audited actions
# from the route modules, and because a console filter keys on it.
ACTION_CONFIG_SET = "config.set"


class ConfigPutRequest(BaseModel):
    """One key at a time, deliberately.

    A whole-doc PUT would make "what changed" a diff the operator has to
    compute, and would let an unrelated stale value in the console's form
    clobber a key someone else just set. One key per request makes the audit
    row's before/after exact and the lost-update window a single field wide.
    """

    key: str
    value: Any


def _validate_channel(channel: str) -> str:
    if channel not in KNOWN_CHANNELS:
        raise HTTPException(
            status_code=404,
            detail="unknown channel {!r}; known channels are {}".format(
                channel, ", ".join(KNOWN_CHANNELS)),
        )
    return channel


def _db():
    """The Firestore client, or a 503.

    Lazy-imported for the same reason every other Firestore caller in this
    repo does it: module import must not require firebase_admin to be
    initialized, so the test suite can import the router freely.
    """
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503,
                            detail="config store unavailable")
    return db


@router.get("/admin/config/{channel}")
async def get_channel_config(
    channel: str,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """The channel's stored config doc, plus the key set that is readable.

    Returns the RAW stored values (not coerced): the console shows an
    operator what is actually in the doc, including a malformed value that
    runtime_config would ignore -- hiding it behind the coercion would make a
    broken setting invisible on the one screen meant to diagnose it.
    `unknown_keys` names entries no backend reads, for the same reason.

    `schema` is {key: {type, default}} for every known key (bd
    polyglot-pdf-wxcj0), from runtime_config.config_schema() -- the console's
    ONLY source for a key's type (bool/int/float), so it renders a select for
    a bool key and a number input for a numeric one without ever hand-listing
    key types itself (CLAUDE.md scar #8).

    A READ, so it writes no audit row. The log records MUTATIONS; auditing
    reads would bury them.
    """
    _validate_channel(channel)
    db = _db()
    try:
        snap = db.collection(runtime_config.COLLECTION).document(channel).get()
    except Exception as exc:  # noqa: BLE001
        _log.error("admin_config_read_failed", channel=channel, error_type=type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail="config store unavailable")
    doc = (snap.to_dict() or {}) if snap.exists else {}
    return {
        "channel": channel,
        "values": doc,
        "known_keys": sorted(runtime_config.RUNTIME_CONFIG_KEYS),
        "unknown_keys": sorted(
            k for k in doc if k not in runtime_config.RUNTIME_CONFIG_KEYS),
        # {key: {type, default}} for every known key (bd polyglot-pdf-wxcj0)
        # -- derived from runtime_config.config_schema(), never a second
        # hand-typed list of key types (CLAUDE.md scar #8), so the console
        # renders a bool key as a select and a numeric key as a number input
        # without this route ever declaring a type of its own.
        "schema": runtime_config.config_schema(),
    }


@router.put("/admin/config/{channel}")
async def put_channel_config(
    channel: str,
    body: ConfigPutRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Set ONE runtime-config key for ONE channel, audited in-transaction.

    Refuses BEFORE any write on an unknown channel (404), an unknown key
    (400), or a value runtime_config's own reader would treat as malformed
    (400) -- the last is the important one: writing such a value would look
    like success in the console while the backend silently kept using the
    previous value.
    """
    _validate_channel(channel)

    if body.key not in runtime_config.RUNTIME_CONFIG_KEYS:
        raise HTTPException(
            status_code=400,
            detail="{!r} is not a runtime config key; valid keys are {}".format(
                body.key, ", ".join(sorted(runtime_config.RUNTIME_CONFIG_KEYS))),
        )

    coerced = runtime_config.coerce_value(body.key, body.value)
    if coerced is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "{!r} is not a valid value for {}; runtime_config would treat "
                "it as malformed and keep the previous value".format(
                    body.value, body.key)),
        )

    db = _db()
    request_id = audit_log.new_request_id()
    result = _apply_config_write(
        db=db,
        channel=channel,
        key=body.key,
        value=coerced,
        actor=actor,
        request_id=request_id,
    )
    _log.info(
        "admin_config_set",
        channel=channel, key=body.key, actor_uid=actor.uid,
        request_id=request_id,
    )
    return {
        "channel": channel,
        "key": body.key,
        "before": result["before"],
        "after": coerced,
        "request_id": request_id,
    }


def _apply_config_write(
    *,
    db,
    channel: str,
    key: str,
    value: Any,
    actor: AdminActor,
    request_id: str,
) -> dict:
    """The config write and its audit row, in ONE Firestore transaction.

    Extracted from the route so the transactional body has a name a test can
    call directly and a reviewer can read without the HTTP layer around it.

    The @firestore.transactional decorator is applied INSIDE this function
    rather than at module scope so the module imports with no firebase_admin
    app initialized, matching every other Firestore caller in this repo.
    """
    from firebase_admin import firestore

    doc_ref = db.collection(runtime_config.COLLECTION).document(channel)
    captured: dict[str, Any] = {}

    @firestore.transactional
    def _txn(tx):
        # The BEFORE read lives inside the transaction on purpose: Firestore
        # re-runs this whole body on contention, and a value read outside
        # would be stale on the retry -- the audit row would then record a
        # `before` that was never the state the write applied to.
        snap = doc_ref.get(transaction=tx)
        existing = (snap.to_dict() or {}) if snap.exists else {}
        before = existing.get(key)
        captured["before"] = before

        # merge=True: one key per request (see ConfigPutRequest), so a write
        # must never drop the channel's other settings.
        tx.set(doc_ref, {key: value}, merge=True)

        # SAME transaction. A failure here aborts the tx.set above with it --
        # that is exit criterion 1's "a forced audit failure leaves the
        # config unchanged".
        audit_log.record_in_transaction(
            tx,
            db,
            actor_uid=actor.uid,
            actor_email=actor.email,
            action=ACTION_CONFIG_SET,
            target="{}/{}#{}".format(runtime_config.COLLECTION, channel, key),
            before={key: before},
            after={key: value},
            channel=channel,
            request_id=request_id,
        )

    try:
        _txn(db.transaction())
    except Exception as exc:  # noqa: BLE001
        _log.error(
            "admin_config_write_failed",
            channel=channel, key=key, error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=500,
                            detail="config write failed") from exc

    return {"before": captured.get("before")}
