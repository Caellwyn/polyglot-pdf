"""Record one deployment row in Firestore deployments/{auto} (bd
polyglot-pdf-ywxoh, Epic 4 bead 4.2 of docs/sprint_22_admin-console_plan.md).

Run by cloudbuild.yaml as the LAST step of every STAGING target
(backend-staging, frontend-staging, admin-service -- see the plan's "The
staging-before-demo gate lives IN THE BUILD" note), so a staging deploy's own
success is durable the moment the build finishes, without racing bead 4.3's
Pub/Sub build-status webhook (which records EVERY build, bash-triggered ones
included, and reconciles by build id once it exists). Bead 4.3's webhook is
additive, not a replacement, because a bash-triggered build (no admin-service
trigger involved) still needs its own success row for the promotion gate to
see.

UPSERT BY build_id, NEVER A BLIND CREATE (fresh-eyes/cross-surface finding,
bd polyglot-pdf-tb3kp). The SAME build_id this step is given
(cloudbuild.yaml's own $BUILD_ID) is also what bead 4.3's Pub/Sub webhook
upserts on (admin_backend/routes/deploy_webhook.py) -- and for a
console-triggered build, Cloud Build publishes QUEUED/WORKING messages
BEFORE this build step ever runs, so the webhook's own row for this exact
build_id typically already exists by the time this script runs. A blind
`.document().set()` (this script's ORIGINAL behavior) would create a
SECOND document carrying the same build_id -- two rows racing to be "the"
row for one build, with a later Pub/Sub message's own `.limit(1)` lookup
picking one non-deterministically and leaving the other's status
permanently stale. This script now queries `deployments` for an existing
row with the given build_id first: if one exists (the console-triggered
case), it UPDATES that row rather than creating a sibling; only a
bash-triggered build (no console row, and typically no webhook row yet
either) falls through to creating a new document, exactly the webhook's
own "UPSERT BY build_id" shape.

FIELDS (docs/sprint_22_admin-console_plan.md, Epic 4 "Triggering and status
from the admin service"): target, target_family, channel, sha, build_id,
status, triggered_by, timestamps. `ref` and `log_url` are bead 4.3's (the
admin-triggered build knows its own git ref and Cloud Build console link;
a bash-triggered build here does not carry either yet).

`ts` IS THE SORT KEY, `created_at` IS THE DISPLAY VALUE (fresh-eyes/
cross-surface finding, bd polyglot-pdf-tb3kp). Bead 4.3's
GET /admin/deploys (admin_backend/routes/deploy_routes.py) orders the whole
`deployments` collection on `ts`, a float Unix epoch -- the SAME type its
own POST route writes via time.time() and bead 4.3's Pub/Sub webhook writes
via its _to_epoch() helper. A row carrying only `created_at` (an ISO-8601
STRING) has no `ts` field at all, and Firestore's order_by() EXCLUDES from
its result set any document missing the ordered-on field -- so without this
field, every staging-success row this script writes (the exact rows the
promotion gate reads, and precisely what authorizes a demo promotion) would
be invisible to the console's deploys list while the gate itself still
passes: a green build, a passing gate, and an operator staring at "no
staging success" in the UI. `created_at` is kept alongside `ts` rather than
replaced -- it is a human-readable string a build log or a future admin
tool can read without float-epoch math, and no other code parses it as a
sort key.

TARGET vs TARGET_FAMILY. "backend-staging" and "backend-demo" are two
TARGETS in the same FAMILY ("backend") -- the promotion gate
(admin_backend/services/promotion_gate.py::staging_verified) matches on
target_family, not target, because a staging deploy of "backend-staging"
is what verifies a DEMO deploy of "backend-demo": same family, different
target, same channel-vs-channel semantics the plan describes as "same
family and sha". target_family is derived here by stripping the trailing
"-staging" / "-demo" suffix; a target with neither suffix (admin-service,
which has no channel of its own) is its own family.

TRIGGERED_BY is always "build" here -- this script runs INSIDE Cloud Build,
so unlike record_build_check.py's `require`, there is no failure-mode reason
to distinguish who kicked it off; bead 4.3's webhook path is what could also
carry "console" or "cli" for the admin-triggered case, and that distinction
lives there, not here.

Fails LOUD, not closed: unlike record_build_check.py's `require` (a missing
verify record must BLOCK every future deploy), a deployment record that fails
to write should not silently make the BUILD look like it never happened --
but it also must not be swallowed as a false "recorded" success. A write
failure exits 1 so the build step itself shows red in the Cloud Build log,
which is the honest signal: the deploy worked, but its own audit row did not
get written, and an operator needs to know that before trusting the
promotion gate's next read.
"""

from __future__ import annotations

import argparse
import datetime
import sys
import time

COLLECTION = "deployments"

# Suffixes cloudbuild.yaml's staging targets carry today. Extending this list
# is a decision for whichever bead adds a target with a different naming
# convention -- see the module docstring's TARGET vs TARGET_FAMILY note.
_CHANNEL_SUFFIXES = ("-staging", "-demo")


def target_family(target: str) -> str:
    """Strip a trailing channel suffix, e.g. "backend-staging" -> "backend".

    A target with neither suffix (e.g. "admin-service", "firestore-rules")
    is its own family unchanged.
    """
    for suffix in _CHANNEL_SUFFIXES:
        if target.endswith(suffix):
            return target[: -len(suffix)]
    return target


def _client(project: str | None):
    """A Firestore client, imported lazily -- see record_build_check.py's
    identical rationale: this is a build-step runtime dependency, not a test
    dependency."""
    from google.cloud import firestore  # noqa: PLC0415

    return firestore.Client(project=project) if project else firestore.Client()


def record(
    target: str,
    channel: str,
    sha: str,
    build_id: str,
    status: str,
    project: str | None,
) -> int:
    fields = {
        "target": target,
        "target_family": target_family(target),
        "channel": channel,
        "sha": sha,
        "build_id": build_id,
        "status": status,
        "triggered_by": "build",
        # Timezone-aware UTC -- same reasoning as record_build_check.py: a
        # naive timestamp read back in another zone silently misreports when
        # this ran.
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        # ts: a float Unix epoch, the SAME type and field name
        # deploy_routes.py's own time.time() writes and deploy_webhook.py's
        # own _to_epoch() writes -- the sort key GET /admin/deploys orders
        # on. See module docstring's "ts IS THE SORT KEY" section: a row
        # with created_at but no ts is invisible to that route's
        # order_by("ts") query.
        "ts": time.time(),
    }
    try:
        collection = _client(project).collection(COLLECTION)
        # UPSERT BY build_id -- see module docstring's "UPSERT BY build_id,
        # NEVER A BLIND CREATE" section. An existing row for this exact
        # build_id (the webhook's own QUEUED/WORKING row, arrived before
        # this build step ran) is UPDATED in place; only a build with no
        # pre-existing row (typically bash-triggered, or a webhook message
        # that has not arrived yet) gets a new document.
        existing = list(
            collection.where("build_id", "==", build_id).limit(1).stream())
        if existing:
            existing[0].reference.update(fields)
        else:
            collection.document().set(fields)
    except Exception as exc:  # noqa: BLE001 -- see module docstring: fail LOUD
        print(
            "[record_deployment] could not write a {} row for target={} "
            "sha={}: {}".format(COLLECTION, target, sha, exc),
            file=sys.stderr,
        )
        return 1
    print(
        "[record_deployment] {} row written: target={} family={} channel={} "
        "sha={} status={} build_id={}".format(
            COLLECTION, target, target_family(target), channel, sha, status,
            build_id,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--status", default="success")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(argv)
    return record(
        args.target, args.channel, args.sha, args.build_id, args.status,
        args.project,
    )


if __name__ == "__main__":
    raise SystemExit(main())
