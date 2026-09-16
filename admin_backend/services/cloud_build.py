"""Trigger a Cloud Build for one target at one commit (bd polyglot-pdf-tb3kp,
Epic 4 bead 4.3 of docs/sprint_22_admin-console_plan.md).

WHAT THIS CALLS AND WHY. run_target(target, sha) runs the manual trigger
"polyglot-<target>" (scripts/setup-cloud-build.sh provisions one per entry
in deploy/targets.py's TARGETS, plus "landing", per that script's own
comment) at an explicit commit, via CloudBuildClient.run_build_trigger.

WHY run_build_trigger, NOT create_build. The bead's own docstring named
create_build as a "preference, not a constraint" pending verification
against the live library docs -- verified here (WebFetch against
docs.cloud.google.com/python/docs/reference/cloudbuild, 2026-09-14):
Build.build_trigger_id is OUTPUT ONLY on the Build resource, so
CreateBuildRequest cannot reference an existing trigger by id at all --
using it would mean respecifying the ENTIRE build config (every step,
image, and substitution cloudbuild.yaml already declares) as a second copy
that could drift from the trigger's own. run_build_trigger's whole point is
the opposite: it re-runs the TRIGGER's own already-configured build
(cloudbuild.yaml, its per-trigger _TARGET/_CHANNEL substitutions) against
just the ONE thing that varies per call, the commit. So this module uses
run_build_trigger exclusively; create_build is not called anywhere here.

THE RepoSource CARRIES ONLY commit_sha, NO repo_name. RepoSource.repo_name
names a Cloud Source Repository (the 1st-generation mechanism) and the
public API reference documents it as "Required" with no stated exception --
but this repo's own 2nd-generation GitHub connection (scripts/
setup-cloud-build.sh's header) is a DIFFERENT resource, bound to the
trigger itself at creation time (--repository=$CLOUD_BUILD_REPOSITORY), not
named per-request. The proven, working CLI shape this repo already
documents as verified ("gcloud builds triggers run TRIGGER --sha=SHA",
scripts/setup-cloud-build.sh's own header, "verified against the current
gcloud reference, 2026-09-11") passes ONLY --sha, no --repo -- gcloud's own
implementation of that flag builds exactly a RepoSource(commit_sha=sha)
with repo_name left unset, letting the server resolve the trigger's OWN
bound repository rather than requiring the caller to re-name it. This
module mirrors that proven shape rather than guessing at repo_name's real
requirement for a 2nd-gen trigger, which neither the REST reference nor the
Python client docs state either way.

THE RepoSource ALSO CARRIES substitutions={"_SHA": sha} (fresh-eyes/
cross-surface finding, bd polyglot-pdf-tb3kp). commit_sha alone is the API
equivalent of `gcloud builds triggers run --sha=SHA` ONLY -- it tells Cloud
Build which commit to check out, but it does NOT populate the `_SHA`
substitution cloudbuild.yaml's own step 0 (require-sha) requires to be
non-empty (that substitution defaults to an empty string in the YAML, and
every trigger this module runs is provisioned with
`--substitutions="_TARGET=...,_CHANNEL=..."` and no `_SHA` at all --
scripts/setup-cloud-build.sh). The documented human invocation ("gcloud
builds triggers run polyglot-verify --sha=<sha> --substitutions=_SHA=<sha>",
that same script's own printed usage) passes BOTH for exactly this reason;
a RepoSource missing `substitutions` makes every console-triggered build
abort at step 0 with "ABORT: _SHA is empty" while this route has already
returned 200 with a real build_id and written a "queued" deployments row
the webhook then flips to "failure" -- 100% of the time, on every target,
with nothing short of watching a build's own log catching it (the route's
own tests mock run_build_trigger entirely).

RETURNS build id + log url, NOT the full Operation/Build message: the
route only needs enough to write deployments/{id}'s build_id and log_url
fields and return control to the caller -- run_build_trigger returns a
long-running google.api_core.operation.Operation, and waiting on it here
would block the request for the FULL BUILD DURATION (~minutes). This module
therefore reads the id and log url off the Operation's METADATA
(BuildOperationMetadata.build), populated as soon as the operation is
created -- before the build itself starts running, let alone finishes --
and does not call operation.result() at all. Status thereafter arrives
asynchronously via bead 4.3's Pub/Sub webhook
(admin_backend/routes/deploy_webhook.py), never by polling this call.

SYNC CLIENT, DISPATCHED WITH asyncio.to_thread BY THE CALLING ROUTE.
CloudBuildClient (like every other google-cloud-* client this service
already uses -- BigQuery, Firestore) is synchronous; the async route
(admin_backend/routes/deploy_routes.py) wraps the call in
asyncio.to_thread, the SAME pattern bigquery_reports.py and
error_stats.py already use for their own synchronous SDK calls.

THE CLIENT IS BUILT LAZILY, PER CALL, matching bigquery_reports.py's own
"not once at import time" rule: module import must not require credentials
to be resolvable, and constructing a CloudBuildClient makes no network call
by itself.

ASCII only.
"""
from __future__ import annotations

import structlog

_log = structlog.get_logger().bind(module="cloud_build")

# "polyglot-<target>" -- the exact trigger-naming convention scripts/
# setup-cloud-build.sh's own TARGETS loop provisions (name="polyglot-$target").
# Restated here as a literal for the same reason every other admin-service
# module keeps its own small constants rather than parsing a shell script at
# import time.
_TRIGGER_NAME_PREFIX = "polyglot-"

# Matches scripts/setup-cloud-build.sh's own CLOUD_BUILD_REGION default --
# a 2nd-generation repository resource cannot live in "global" (that
# script's own "REGION IS NOT OPTIONAL" comment), so every trigger this
# module addresses was created in, and must be run in, this region.
DEFAULT_REGION = "us-central1"


class CloudBuildUnavailable(Exception):
    """The google-cloud-build client could not be constructed, or the
    run_build_trigger call itself failed (network, auth, an unknown trigger
    name, a malformed request). Mapped to a 503 by the calling route,
    mirroring bigquery_reports.BigQueryUnavailable and admin_auth.
    OidcVerificationUnavailable's identical polarity: a caller must be able
    to tell "the trigger machinery itself could not run" apart from a
    business-rule refusal (422/409), which this exception is never raised
    for.
    """


def _client(*, region: str):
    """A CloudBuildClient talking to the REGIONAL endpoint a 2nd-generation
    trigger lives in -- the default (global) endpoint the client otherwise
    constructs cannot address a regional resource at all. Built lazily, per
    call: see module docstring."""
    from google.api_core.client_options import ClientOptions
    from google.cloud.devtools import cloudbuild_v1

    return cloudbuild_v1.CloudBuildClient(
        client_options=ClientOptions(
            api_endpoint="{}-cloudbuild.googleapis.com".format(region)),
    )


def run_target(
    target: str,
    sha: str,
    *,
    project_id: str,
    region: str = DEFAULT_REGION,
) -> dict:
    """Run the "polyglot-<target>" trigger at commit `sha`.

    Returns {"build_id": str, "log_url": str}. `target` is trusted to
    already be validated against deploy/targets.py's TARGETS (the route's
    job, not this module's -- this function has no opinion on which target
    names are legal, only on how to run whichever one it is given). `sha`
    is trusted to already be validated as 40 hex characters (also the
    route's job).

    Raises CloudBuildUnavailable on any failure to construct the client or
    complete the RPC -- see that class's docstring for the 503 mapping.
    """
    from google.cloud.devtools import cloudbuild_v1

    trigger_name = _TRIGGER_NAME_PREFIX + target
    try:
        client = _client(region=region)
        operation = client.run_build_trigger(
            request=cloudbuild_v1.RunBuildTriggerRequest(
                # name= is what makes this a REGIONAL run. The request also
                # carries project_id/trigger_id, and the REST transport tries
                # its URI templates IN ORDER: the project/trigger pair alone
                # matches the global-only
                # "/v1/projects/{project_id}/triggers/{trigger_id}:run"
                # template first, so a request without `name` addresses the
                # GLOBAL trigger registry no matter which regional endpoint
                # the client points at -- and every trigger this repo
                # provisions is regional (scripts/setup-cloud-build.sh's
                # "REGION IS NOT OPTIONAL"), so it would 404 as "trigger not
                # found". Setting `name` selects the regional template.
                name="projects/{}/locations/{}/triggers/{}".format(
                    project_id, region, trigger_name),
                project_id=project_id,
                trigger_id=trigger_name,
                source=cloudbuild_v1.RepoSource(
                    # NO repo_name -- see module docstring's "RepoSource
                    # CARRIES ONLY commit_sha" section for why this mirrors
                    # the proven gcloud --sha=SHA CLI shape rather than
                    # guessing at a 2nd-gen value for that field.
                    commit_sha=sha,
                    # _SHA substitution -- see module docstring's "THE
                    # RepoSource ALSO CARRIES substitutions" section.
                    # Without this, cloudbuild.yaml's require-sha step (the
                    # build's own step 0) aborts every console-triggered
                    # build before anything else runs.
                    substitutions={"_SHA": sha},
                ),
            ),
        )
    except Exception as exc:  # noqa: BLE001 -- see CloudBuildUnavailable's
        # docstring: every failure mode here (bad credentials, an unknown
        # trigger name, a network blip, a malformed request the client
        # library itself rejects) collapses to the SAME "the trigger
        # machinery could not run" signal for the caller; the route logs
        # the real exception text server-side before translating it.
        _log.error(
            "cloud_build_run_trigger_failed",
            target=target, trigger_name=trigger_name, error=str(exc),
        )
        raise CloudBuildUnavailable(
            "could not run trigger {!r}: {}".format(trigger_name, exc)
        ) from exc

    # BuildOperationMetadata.build is populated the moment the operation is
    # CREATED (the build is enqueued), well before it starts running or
    # finishes -- this module never calls operation.result(), which would
    # block for the whole build duration. See module docstring.
    build = operation.metadata.build
    build_id = build.id
    log_url = build.log_url

    _log.info(
        "cloud_build_run_trigger_started",
        target=target, trigger_name=trigger_name, sha=sha,
        build_id=build_id,
    )

    return {"build_id": build_id, "log_url": log_url}
