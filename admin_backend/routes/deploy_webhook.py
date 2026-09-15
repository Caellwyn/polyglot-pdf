"""POST /api/deploys/webhook -- the Pub/Sub push endpoint for Cloud Build's
build-status notifications (bd polyglot-pdf-tb3kp, Epic 4 bead 4.3 of
docs/sprint_22_admin-console_plan.md).

WHAT THIS IS. Cloud Build publishes a message to the `cloud-builds` topic on
every state change of every build in the project -- console-triggered
(bead 4.3's own POST /admin/deploys) AND bash-triggered (an operator running
`gcloud builds triggers run ... --sha=...` directly), one message per state
transition. A Pub/Sub PUSH subscription (scripts/setup-admin-service.sh)
delivers each message here as an HTTP POST; this route decodes it, updates
deployments/{id} BY BUILD ID (never by re-deriving an id from the message),
and always returns 204 on a well-formed message so Pub/Sub's own retry
policy leaves it alone -- a non-2xx response makes Pub/Sub redeliver the
SAME message indefinitely (per Google's own push-subscription semantics),
which would multiply a transient Firestore hiccup into a redelivery storm.

GATE: require_google_oidc(audience, allowed_caller_emails), mirroring
sweep_routes.py's shape exactly -- THIS route's own URL as audience (this
service's PUBSUB_PUSH_SA_EMAIL-authenticated push subscription, configured
with `--push-auth-service-account=<pubsub-push-sa>
--push-auth-token-audience=<this route's URL>`), and the push subscription's
service-account email as the sole allowed caller (config env
PUBSUB_PUSH_SA_EMAIL, read the SAME way sweep_routes.py reads
SWEEP_SCHEDULER_SA_EMAIL -- a zero-arg callable passed to the factory, so a
route-module-import-time env read never freezes in an unconfigured value
before a real deploy has set it). This is require_google_oidc's SECOND
consuming route (its first was POST /admin/links/sweep-expired, bd
polyglot-pdf-8vgfh) -- see admin_backend/services/admin_auth.py's own "WHY
AUDIENCE ALONE DOES NOT PROVE THE CALLER" section for why the email pin is
load-bearing, not redundant with a public Cloud Run service's own audience
check.

MESSAGE SHAPE (Pub/Sub's own push envelope, NOT Cloud Build's build
resource laid out flat): {"message": {"data": "<base64>", "attributes":
{...}, "messageId": "..."}, "subscription": "..."}. `data` is the
BASE64-ENCODED JSON of the Cloud Build Build resource itself (id, status,
substitutions, logUrl, startTime/finishTime, ...) -- Cloud Build's own
documented Pub/Sub notification shape.

UPSERT BY build_id, NEVER BY DOCUMENT ID. A console-triggered build already
has a deployments/{id} row (bd 4.3's own POST /admin/deploys writes it with
status "queued" BEFORE the Cloud Build call even returns) keyed by an
AUTO-GENERATED Firestore id that has nothing to do with the build's own id
-- so this route QUERIES deployments where build_id == <the message's
build id>, and updates the FIRST (and, by construction, only) match. A
bash-triggered build has NO pre-existing row at all: this route creates one,
with triggered_by "external" (never a uid -- nobody in this system claims
credit for a build the console did not trigger) and target/channel read out
of the build's OWN substitutions (_TARGET, _CHANNEL) rather than left blank,
since the build message carries them and a blank field would make the
console's list view show an unexplained row.

IDEMPOTENT. Pub/Sub's own delivery guarantee is AT LEAST ONCE -- the same
messageId can arrive twice. This route's update is a plain field-value SET
keyed by build_id + the message's OWN status/timestamps, not an increment or
an append: applying the identical message twice produces the identical
document, so no dedup ledger is needed (contrast bead A5's refund sweep,
which dedups because a refund is an INCREMENT of a balance -- this route
never adds to anything, it only overwrites a row with the latest state THAT
MESSAGE describes).

STATUS MAPPING. Cloud Build's Build.Status enum has more values than this
collection's own five-way `status` field (queued | working | success |
failure | cancelled, deploy_routes.py's own STATUS_* constants) needs --
QUEUE, WORKING map straight across; SUCCESS -> success; FAILURE, INTERNAL_
ERROR, TIMEOUT, EXPIRED all collapse to "failure" (the console's own list
view distinguishes them no further than "did it fail", and Cloud Build's own
log carries the detailed reason); CANCELLED -> cancelled. An UNRECOGNIZED
status string (a future Cloud Build enum value this route does not yet
know) maps to "failure" rather than silently keeping the pre-existing
status or crashing -- a build in a state this route cannot name is closer to
"something is wrong" than to "still queued".

ALWAYS 204 ON A WELL-FORMED MESSAGE (module docstring's own "WHAT THIS IS"
paragraph). A message this route cannot even PARSE (malformed base64,
missing required fields) is a genuine 400 -- Pub/Sub does not redeliver
faster for a 400 than a 500, and a 400 is at least visible in this
service's own request logs as "a message Cloud Build itself would never
have sent", worth investigating differently than "Firestore was briefly
unreachable".

ASCII only.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import time
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response

from admin_backend.services import audit_log
from admin_backend.services.admin_auth import (
    GoogleServiceActor,
    require_google_oidc,
)

_log = structlog.get_logger().bind(module="admin_deploy_webhook")

router = APIRouter()

COLLECTION = "deployments"

ACTION_DEPLOY_STATUS_UPDATE = "deploy.status_update"

# The actor stamped on every audit row this webhook writes -- Cloud
# Build via Pub/Sub, never an operator. Same "system:" convention as
# sweep_routes.SWEEP_ACTOR.
WEBHOOK_ACTOR = "system:cloud_build_webhook"

_WEBHOOK_ROUTE_PATH = "/api/deploys/webhook"

# Cloud Build's own Build.Status enum values (google.devtools.cloudbuild.v1
# .Build.Status), as the raw uppercase strings the JSON payload carries --
# mapped to this collection's five-way status vocabulary. An enum value not
# in this map (a future Cloud Build status this route does not yet know)
# falls through to STATUS_FAILURE via .get()'s default -- see module
# docstring's "STATUS MAPPING" section.
STATUS_QUEUED = "queued"
STATUS_WORKING = "working"
STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_CANCELLED = "cancelled"

_BUILD_STATUS_MAP = {
    "QUEUED": STATUS_QUEUED,
    "WORKING": STATUS_WORKING,
    "SUCCESS": STATUS_SUCCESS,
    "FAILURE": STATUS_FAILURE,
    "INTERNAL_ERROR": STATUS_FAILURE,
    "TIMEOUT": STATUS_FAILURE,
    "EXPIRED": STATUS_FAILURE,
    "CANCELLED": STATUS_CANCELLED,
}

_TERMINAL_STATUSES = frozenset(
    {STATUS_SUCCESS, STATUS_FAILURE, STATUS_CANCELLED})


def _mapped_status(raw_status: Optional[str]) -> str:
    return _BUILD_STATUS_MAP.get((raw_status or "").upper(), STATUS_FAILURE)


def _audience() -> str:
    """This route's own URL -- see sweep_routes.py's identical _audience()
    for the full rationale (root+path, never hard-coded, resolved fresh
    per-request so a route module import before ADMIN_SERVICE_URL is set
    does not freeze in an empty value).
    """
    root = os.getenv("ADMIN_SERVICE_URL", "")
    return root + _WEBHOOK_ROUTE_PATH if root else ""


def _allowed_caller_emails() -> tuple:
    """The Pub/Sub push subscription's service-account email -- see module
    docstring's GATE section. Empty when unset, allowlisting nothing (fail
    CLOSED), same shape as sweep_routes.py's _allowed_caller_emails.
    """
    email = os.getenv("PUBSUB_PUSH_SA_EMAIL", "")
    return (email,) if email else tuple()


def _db():
    from backend.services.auth import get_db

    return get_db()


def _decode_build_message(body: dict) -> dict:
    """The Cloud Build Build resource carried in a Pub/Sub push envelope's
    base64 `message.data`, or raise ValueError for a malformed message.

    Mapped to a 400 by the route -- see module docstring's "ALWAYS 204 ON A
    WELL-FORMED MESSAGE" section for why a message this route cannot even
    parse is the one case that is NOT a 204.
    """
    message = body.get("message")
    if not isinstance(message, dict):
        raise ValueError("no 'message' object in the push envelope")
    raw_data = message.get("data")
    if not isinstance(raw_data, str) or not raw_data:
        raise ValueError("'message.data' is missing or not a string")
    try:
        decoded = base64.b64decode(raw_data)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("'message.data' is not valid base64: {}".format(
            exc)) from exc
    try:
        build = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "'message.data' did not decode to JSON: {}".format(exc)) from exc
    if not isinstance(build, dict):
        raise ValueError("the decoded build payload is not a JSON object")
    build_id = build.get("id")
    if not build_id or not isinstance(build_id, str):
        raise ValueError("the build payload carries no string 'id'")
    return build


def _target_family(target):
    if not target:
        return None
    for suffix in ("-staging", "-demo"):
        if target.endswith(suffix):
            return target[: -len(suffix)]
    return target


def _upsert_deployment(db, build: dict) -> None:
    """Update-by-build_id, or create for a bash-triggered build with no
    pre-existing row. See module docstring's "UPSERT BY build_id" section.

    THIS IS A FIRESTORE MUTATION, so it audits IN THE SAME TRANSACTION as
    the write (admin_backend/services/audit_log.py's "FORM 1" -- mirrors
    firm_routes.py's _apply_firm_patch shape exactly: read (the existing-
    row lookup), write, audit, all three inside ONE @firestore.transactional
    body). actor_uid is "system:cloud_build_webhook", the same "system:"
    convention sweep_routes.SWEEP_ACTOR uses for a machine-triggered write
    nobody signed into the console: this route's caller is Cloud Build via
    Pub/Sub, never an operator, and the audit row's actor field says so
    plainly rather than naming nobody.
    """
    from firebase_admin import firestore

    build_id = build["id"]
    raw_status = build.get("status")
    status = _mapped_status(raw_status)
    log_url = build.get("logUrl")
    substitutions = build.get("substitutions") or {}
    target = substitutions.get("_TARGET")
    channel = substitutions.get("_CHANNEL")
    sha = substitutions.get("_SHA") or build.get("sourceProvenance", {}).get(
        "resolvedRepoSource", {}).get("commitSha")

    finished_at = None
    if status in _TERMINAL_STATUSES:
        finished_at = build.get("finishTime") or time.time()

    collection = db.collection(COLLECTION)
    update_fields = {
        "build_id": build_id,
        "status": status,
        "log_url": log_url,
        "finished_at": finished_at,
    }

    @firestore.transactional
    def _txn(tx):
        # THE READ LIVES INSIDE THE TRANSACTION (mirrors config_routes.py
        # and firm_routes.py): Firestore re-runs this whole body on
        # contention, and a lookup done outside would go stale on a retry.
        existing = list(
            collection.where("build_id", "==", build_id).limit(1)
            .stream(transaction=tx))
        request_id = audit_log.new_request_id()

        if existing:
            ref = existing[0].reference
            before = existing[0].to_dict() or {}
            tx.update(ref, update_fields)
            audit_log.record_in_transaction(
                tx, db,
                actor_uid=WEBHOOK_ACTOR, actor_email=None,
                action=ACTION_DEPLOY_STATUS_UPDATE,
                target="{}/{}".format(COLLECTION, ref.id),
                before={"status": before.get("status")},
                after={"status": status, "build_id": build_id},
                channel=before.get("channel"),
                request_id=request_id,
            )
            _log.info(
                "admin_deploy_webhook_updated", build_id=build_id,
                status=status, raw_status=raw_status,
            )
            return

        # A BASH-TRIGGERED BUILD: no console row exists. Create one with
        # triggered_by "external" -- see module docstring's "UPSERT BY
        # build_id" section for why target/channel come from the build's
        # OWN substitutions rather than being left blank.
        ref = collection.document()
        row = {
            "target": target,
            "target_family": _target_family(target),
            "channel": channel,
            "sha": sha,
            "ref": None,
            "triggered_by": "external",
            "ts": build.get("createTime") or time.time(),
            **update_fields,
        }
        tx.set(ref, row)
        audit_log.record_in_transaction(
            tx, db,
            actor_uid=WEBHOOK_ACTOR, actor_email=None,
            action=ACTION_DEPLOY_STATUS_UPDATE,
            target="{}/{}".format(COLLECTION, ref.id),
            before=None,
            after={"status": status, "build_id": build_id,
                  "triggered_by": "external"},
            channel=channel,
            request_id=request_id,
        )
        _log.info(
            "admin_deploy_webhook_created_external", build_id=build_id,
            status=status, raw_status=raw_status, target=target,
        )

    _txn(db.transaction())


_webhook_oidc_gate = require_google_oidc(
    audience=_audience,
    allowed_caller_emails=_allowed_caller_emails,
)


@router.post("/api/deploys/webhook")
async def deploy_status_webhook(
    body: dict,
    actor: Annotated[GoogleServiceActor, Depends(_webhook_oidc_gate)] = None,
) -> Response:
    """The Pub/Sub push endpoint. See module docstring."""
    try:
        build = _decode_build_message(body)
    except ValueError as exc:
        _log.warning("admin_deploy_webhook_malformed_message", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db = _db()
    if db is None:
        # Firestore itself is unreachable -- NOT a malformed message. A 503
        # (unlike the 400 above) IS one Pub/Sub will retry, which is exactly
        # what should happen for a transient store outage.
        raise HTTPException(status_code=503, detail="deploy store unavailable")

    _upsert_deployment(db, build)

    _log.info(
        "admin_deploy_webhook_processed",
        build_id=build["id"], caller_email=actor.email if actor else None,
    )
    return Response(status_code=204)
