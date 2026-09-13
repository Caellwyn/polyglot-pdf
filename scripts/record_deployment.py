"""Record one deployment row in Firestore deployments/{auto} (bd
polyglot-pdf-ywxoh, Epic 4 bead 4.2 of docs/sprint_22_admin-console_plan.md).

Run by cloudbuild.yaml as the LAST step of every STAGING target
(backend-staging, frontend-staging, admin-service -- see the plan's "The
staging-before-demo gate lives IN THE BUILD" note), so a staging deploy's own
success is durable the moment the build finishes, without racing bead 4.3's
Pub/Sub build-status webhook (which records EVERY build, bash-triggered ones
included, and reconciles by build id once it exists). Until 4.3 ships, this
script is the ONLY writer of `deployments` -- the webhook is additive, not a
replacement, because a bash-triggered build (no admin-service trigger
involved) still needs its own success row for the promotion gate to see.

FIELDS (docs/sprint_22_admin-console_plan.md, Epic 4 "Triggering and status
from the admin service"): target, target_family, channel, sha, build_id,
status, triggered_by, timestamps. `ref` and `log_url` are bead 4.3's (the
admin-triggered build knows its own git ref and Cloud Build console link;
a bash-triggered build here does not carry either yet).

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
    doc = {
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
    }
    try:
        _client(project).collection(COLLECTION).document().set(doc)
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
