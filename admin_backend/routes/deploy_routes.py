"""POST/GET /admin/deploys -- trigger a Cloud Build and read back what has
run (bd polyglot-pdf-tb3kp, Epic 4 bead 4.3 of
docs/sprint_22_admin-console_plan.md; the two GET reads below are E4.7, bd
polyglot-pdf-ryx86, added for the console's Deploys page).

FIVE ROUTES:

    POST /admin/deploys                trigger a build for {target, sha}
    GET  /admin/deploys                list deployments, newest first
    GET  /admin/deploys/targets        the closed target-picker list
    GET  /admin/deploys/promotable     would {target, sha} pass the gate
    GET  /admin/deploys/{id}           read one deployment

ALL FIVE behind require_app_admin -- deploying code is not a firm-manager
operation; there is no owning-manager counterpart here, same shape as
firm_routes.py's six routes.

GET /admin/deploys/targets AND GET /admin/deploys/promotable ARE REGISTERED
ON THIS ROUTER BEFORE GET /admin/deploys/{deploy_id} (bd polyglot-pdf-ryx86):
FastAPI/Starlette match routes in REGISTRATION order, and `{deploy_id}` is a
bare path parameter that would otherwise swallow a request for the literal
path segment "targets" or "promotable" as an attempted deploy-id lookup (a
404 "No such deployment" instead of the real response) -- the two literal
routes must be added ahead of the parameterized one for exactly that reason.

GET /admin/deploys/targets EXISTS SO THE CONSOLE'S TRIGGER-FORM PICKER NEVER
HAND-COPIES deploy/targets.py::TARGETS (bd polyglot-pdf-ryx86, E4.7) -- the
same "one closed list, not a second hand-typed copy" reasoning `_validated_
target` already applies to POST's own validation now extends to the picker a
console renders from. Each row restates target/target_family/channel/gated
so the console can group and label the picker without a second lookup table
of its own.

GET /admin/deploys/promotable COMPUTES THE SAME staging_verified() PREDICATE
POST /admin/deploys' own early 409 uses (bd polyglot-pdf-ryx86, E4.7) -- so
the console's Deploy button can disable itself with a friendly reason BEFORE
ever POSTing and hitting that 409. A target OUTSIDE GATED_TARGETS is
unconditionally `promotable: true`: POST's own early check applies no gate
to it either (see GATED_TARGETS' own docstring in deploy/targets.py), so
this read must not invent a stricter rule than the route it is a preview
of. `_staging_verified_for()` below is the ONE query both this route and
`_do_trigger_deploy`'s early check call, so the two can never drift into
checking slightly different things.

POST validates target against deploy/targets.py's closed TARGETS (422 on an
unknown value -- never silently running an arbitrary trigger name) and sha
as exactly 40 lowercase hex characters (422 otherwise: a short or
uppercase-mixed value is never a real git SHA this repo's own `git
rev-parse HEAD` would produce). For a target in deploy/targets.py's
GATED_TARGETS (backend-demo, frontend-demo, admin-service), it calls
admin_backend.services.promotion_gate.staging_verified(target_family, sha,
...) BEFORE ever touching Cloud Build -- exit criterion 3's "early, friendly
409": the build's own in-build gate (scripts/promotion_gate.py, bd
polyglot-pdf-ywxoh) repeats the identical check, so a bash-triggered build
still cannot bypass it, but this route's job is giving the console operator
an immediate, readable refusal rather than a build that fails five minutes
in with a log they have to go find.

WRITE ORDER (exit criterion 1): the deployments/{id} row is written FIRST,
status "queued", with no build_id yet -- then the audit row (pending-then-
committed, since triggering a build is a NON-FIRESTORE mutation: the actual
side effect is a Cloud Build API call, not a Firestore write, matching
user_routes.py's create_user shape exactly) -- then Cloud Build is called.
On success, BOTH the deployment row (build_id, log_url) and the audit row
(mark_committed) are updated with the real build id. On failure, the audit
row is marked failed and the deployment row's status is corrected to
"failure" with no build_id -- exit criterion 1's "a failure marks the audit
row failed and leaves no queued row claiming a build id": the row still
EXISTS (a caller's attempted trigger is not erased), but it can never be
mistaken for a build that is actually running, because it names no build id
and its status says failure, not queued.

GET /admin/deploys is DELIBERATELY CLIENT-SIDE FILTERED on channel/target,
not two more Firestore composite indexes: this collection is low-volume
(one row per deploy, an operator/console action, not a per-request write)
and the route already reads a `limit`-capped page ordered by ts DESC (a
single-field index Firestore creates automatically) -- adding channel/target
as FieldFilter .where() clauses would need their own composite indexes
(mirroring GET /admin/audit's discipline, admin_backend/tests/unit/
test_firestore_indexes.py) for a collection this bead's own Surfaces list
does not name that test file for. A future bead that needs richer filtering
on a much larger deployments collection can add the composite indexes then;
this bead trades a slightly larger read (capped by limit's own upper bound)
for not touching a file outside its declared scope.

RESPONSE ROWS ARE AN EXPLICIT KEY ALLOWLIST (DEPLOYMENT_VIEW_FIELDS), never
**doc -- matching link_routes.py's own "a future internal field on either
stored document cannot leak" rule.

ASCII only.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from admin_backend.services import audit_log, cloud_build
from admin_backend.services.admin_auth import AdminActor, require_app_admin
from admin_backend.services.promotion_gate import staging_verified
from deploy.targets import CHANNEL_BY_TARGET, GATED_TARGETS, TARGETS, target_family

_log = structlog.get_logger().bind(module="admin_deploy_routes")

router = APIRouter()

COLLECTION = "deployments"

ACTION_DEPLOY_TRIGGER = "deploy.trigger"

# Cloud Build's own status vocabulary, restated here as the closed set this
# service's OWN "queued" starting status plus the webhook's mapped values
# (bd polyglot-pdf-tb3kp's deploy_webhook.py) can ever be. "queued" is what
# THIS route writes before Cloud Build has said anything at all; the other
# four are what the webhook maps a real Build.Status onto.
STATUS_QUEUED = "queued"
STATUS_WORKING = "working"
STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_CANCELLED = "cancelled"

# A git commit SHA, and nothing looser: exactly 40 lowercase hex characters,
# matching what `git rev-parse HEAD` actually produces (never uppercase, and
# never the 7-char short form a human might paste). deploy-all.sh's own
# `GIT_SHA=$(git rev-parse HEAD)` and cloudbuild.yaml's `$COMMIT_SHA` both
# produce this exact shape.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# The explicit response-row allowlist (exit criterion, "explicit key
# allowlist") -- never **doc, so a future internal field on the stored
# document (an operator note, a retry counter) cannot leak to the console
# without a deliberate addition here.
DEPLOYMENT_VIEW_FIELDS = (
    "id",
    "target",
    "target_family",
    "channel",
    "sha",
    "ref",
    "triggered_by",
    "build_id",
    "status",
    "log_url",
    "ts",
    "finished_at",
)


class TriggerDeployRequest(BaseModel):
    target: str
    sha: str


def _db():
    """The Firestore client both the deployments collection and the audit
    log write through, or a 503. Mirrors user_routes.py's own _db()."""
    from backend.services.auth import get_db

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="deploy store unavailable")
    return db


def _validated_target(target: str) -> str:
    if target not in TARGETS:
        raise HTTPException(
            status_code=422,
            detail="unknown target {!r}; known targets are {}".format(
                target, ", ".join(TARGETS)),
        )
    return target


def _validated_sha(sha: str) -> str:
    if not _SHA_RE.fullmatch(sha):
        raise HTTPException(
            status_code=422,
            detail="sha must be exactly 40 lowercase hex characters",
        )
    return sha


def _project_id() -> str:
    """The GCP project id this service runs in, from google.auth's own ADC
    resolution -- same pattern as error_stats.py's own _project_id (never
    hard-coded, so this route works identically in whatever project a
    deploy actually lands in)."""
    import google.auth

    try:
        _, project = google.auth.default()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail="could not resolve the deployed project id") from exc
    if not project:
        raise HTTPException(
            status_code=503, detail="ADC resolved no project id")
    return project


def _public_view(doc_id: str, data: dict) -> dict:
    row = {"id": doc_id}
    for field in DEPLOYMENT_VIEW_FIELDS:
        if field == "id":
            continue
        row[field] = data.get(field)
    return row


def _staging_verified_for(family: str, sha: str) -> bool:
    """The ONE query both `_do_trigger_deploy`'s early refusal and GET
    /admin/deploys/promotable (bd polyglot-pdf-ryx86, E4.7) run: every
    `deployments` row for this exact (target_family, sha), handed to
    `promotion_gate.staging_verified()`. A shared helper so the route's
    early 409 and the console's own preview read can never drift into
    checking slightly different things.
    """
    db = _db()
    query = (
        db.collection(COLLECTION)
        .where("target_family", "==", family)
        .where("sha", "==", sha)
    )
    deployments = [doc.to_dict() or {} for doc in query.stream()]
    return staging_verified(family, sha, deployments)


def _do_trigger_deploy(
    *, target: str, sha: str, actor_uid: str, actor_email: Optional[str],
) -> dict:
    """The synchronous body of POST /admin/deploys -- see module docstring's
    "WRITE ORDER" section for the exact sequence and why a failure never
    leaves a queued row claiming a build id.
    """
    db = _db()
    channel = CHANNEL_BY_TARGET[target]
    family = target_family(target)

    # THE EARLY, FRIENDLY REFUSAL (exit criterion 3). Only for GATED_TARGETS
    # -- see deploy/targets.py's own docstring for why this is a hand-listed
    # set, not every "demo channel" target.
    if target in GATED_TARGETS:
        if not _staging_verified_for(family, sha):
            raise HTTPException(
                status_code=409,
                detail=(
                    "no successful staging deployment found for family "
                    "{!r} sha {!r} -- deploy to staging first".format(
                        family, sha)
                ),
            )

    now = time.time()
    deploy_ref = db.collection(COLLECTION).document()
    deploy_ref.set({
        "target": target,
        "target_family": family,
        "channel": channel,
        "sha": sha,
        "ref": None,
        "triggered_by": actor_uid,
        "build_id": None,
        "status": STATUS_QUEUED,
        "log_url": None,
        "ts": now,
        "finished_at": None,
    })

    request_id = audit_log.new_request_id()
    audit_ref = audit_log.record_pending(
        db,
        actor_uid=actor_uid,
        actor_email=actor_email,
        action=ACTION_DEPLOY_TRIGGER,
        target="{}/{}".format(COLLECTION, deploy_ref.id),
        before=None,
        after={"target": target, "sha": sha, "channel": channel},
        request_id=request_id,
    )

    try:
        result = cloud_build.run_target(
            target, sha, project_id=_project_id())
    except cloud_build.CloudBuildUnavailable as exc:
        audit_log.mark_failed(audit_ref, error=str(exc))
        # NO build_id, and the status is corrected away from "queued" -- see
        # module docstring's "WRITE ORDER": the row stays (a caller's
        # attempted trigger is not erased) but can never be mistaken for a
        # build that is actually running.
        deploy_ref.update({"status": STATUS_FAILURE})
        _log.error("admin_deploy_trigger_failed", target=target, sha=sha,
                   error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="could not trigger the build") from exc

    deploy_ref.update({
        "build_id": result["build_id"], "log_url": result["log_url"],
    })
    audit_log.mark_committed(audit_ref, after={
        "target": target, "sha": sha, "channel": channel,
        "build_id": result["build_id"],
    })

    _log.info(
        "admin_deploy_triggered", target=target, sha=sha, channel=channel,
        build_id=result["build_id"], actor_uid=actor_uid,
    )

    row = _public_view(deploy_ref.id, {
        "target": target, "target_family": family, "channel": channel,
        "sha": sha, "ref": None, "triggered_by": actor_uid,
        "build_id": result["build_id"], "status": STATUS_QUEUED,
        "log_url": result["log_url"], "ts": now, "finished_at": None,
    })
    row["request_id"] = request_id
    return row


def _do_list_deploys(
    *, channel: Optional[str], target: Optional[str], limit: int,
) -> list[dict]:
    """Newest-first deployments, client-side filtered on channel/target --
    see module docstring's "GET /admin/deploys is DELIBERATELY CLIENT-SIDE
    FILTERED" section for why.
    """
    db = _db()
    # Fetch newest-first (single-field ts index, auto-created) up to a
    # generous multiple of `limit` so a filtered result still fills the
    # page when recent rows happen to miss the filter -- capped, never
    # unbounded, so a filter that matches almost nothing cannot turn this
    # into a full collection scan.
    fetch_cap = max(limit * 5, 50)
    query = (
        db.collection(COLLECTION)
        .order_by("ts", direction="DESCENDING")
        .limit(fetch_cap)
    )
    rows = []
    for doc in query.stream():
        data = doc.to_dict() or {}
        if channel is not None and data.get("channel") != channel:
            continue
        if target is not None and data.get("target") != target:
            continue
        rows.append(_public_view(doc.id, data))
        if len(rows) >= limit:
            break
    return rows


def _do_get_deploy(deploy_id: str) -> dict:
    db = _db()
    snap = db.collection(COLLECTION).document(deploy_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="No such deployment")
    return _public_view(snap.id, snap.to_dict() or {})


@router.post("/admin/deploys")
async def trigger_deploy(
    body: TriggerDeployRequest,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Trigger a Cloud Build for {target, sha}. See module docstring."""
    target = _validated_target(body.target)
    sha = _validated_sha(body.sha)
    return await asyncio.to_thread(
        _do_trigger_deploy,
        target=target, sha=sha, actor_uid=actor.uid, actor_email=actor.email,
    )


@router.get("/admin/deploys")
async def list_deploys(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    channel: Optional[str] = Query(default=None),
    target: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List deployments, newest first. A read, so no audit row."""
    if target is not None and target not in TARGETS:
        raise HTTPException(
            status_code=422,
            detail="unknown target {!r}; known targets are {}".format(
                target, ", ".join(TARGETS)),
        )
    rows = await asyncio.to_thread(
        _do_list_deploys, channel=channel, target=target, limit=limit)
    return {"rows": rows}


@router.get("/admin/deploys/targets")
async def list_deploy_targets(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """The closed target set the trigger form's picker renders from (bd
    polyglot-pdf-ryx86, E4.7) -- see module docstring's "GET /admin/deploys/
    targets" section. Never hand-copied into the console: this is the ONE
    place `deploy/targets.py::TARGETS` reaches the frontend. A read, so no
    audit row.

    MUST STAY REGISTERED AHEAD OF GET /admin/deploys/{deploy_id} on this
    router -- see module docstring.
    """
    rows = [
        {
            "target": target,
            "target_family": target_family(target),
            "channel": CHANNEL_BY_TARGET[target],
            "gated": target in GATED_TARGETS,
        }
        for target in TARGETS
    ]
    return {"targets": rows}


@router.get("/admin/deploys/promotable")
async def get_promotable(
    actor: Annotated[AdminActor, Depends(require_app_admin)],
    target: Annotated[str, Query()],
    sha: Annotated[str, Query()],
) -> dict:
    """Would {target, sha} pass POST /admin/deploys' own early promotion
    gate (bd polyglot-pdf-ryx86, E4.7)? See module docstring's "GET
    /admin/deploys/promotable" section. `target`/`sha` are REQUIRED query
    params (422 via FastAPI's own validation when either is missing) and
    validated exactly like the trigger route's own body (422 on an unknown
    target or a malformed sha). A read, so no audit row.

    MUST STAY REGISTERED AHEAD OF GET /admin/deploys/{deploy_id} on this
    router -- see module docstring.
    """
    target = _validated_target(target)
    sha = _validated_sha(sha)
    family = target_family(target)
    gated = target in GATED_TARGETS
    if gated:
        promotable = await asyncio.to_thread(
            _staging_verified_for, family, sha)
    else:
        # POST's own early check applies no gate to a target outside
        # GATED_TARGETS -- this preview must not invent a stricter rule
        # than the route it previews (module docstring).
        promotable = True
    return {
        "target": target,
        "sha": sha,
        "target_family": family,
        "gated": gated,
        "promotable": promotable,
    }


@router.get("/admin/deploys/{deploy_id}")
async def get_deploy(
    deploy_id: str,
    actor: Annotated[AdminActor, Depends(require_app_admin)],
) -> dict:
    """Read one deployment row. A read, so no audit row."""
    return await asyncio.to_thread(_do_get_deploy, deploy_id)
