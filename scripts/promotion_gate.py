"""CLI over admin_backend.services.promotion_gate.staging_verified, for
cloudbuild.yaml's demo targets (bd polyglot-pdf-ywxoh, Epic 4 bead 4.2 of
docs/sprint_22_admin-console_plan.md; the predicate itself is a placeholder
bead 4.4 extends -- see that module's docstring).

THIS IS A THIN CLI, not a second implementation of the rule. It queries
Firestore's `deployments` collection for the given target_family, hands the
rows to staging_verified() unchanged, and translates the boolean into an exit
code -- so the build-side gate and the (future) admin-route gate in bead 4.4
can never disagree about what "verified" means; only this module's Firestore
query is build-specific.

Run by cloudbuild.yaml as the FIRST real step (after the build_checks gate)
of every DEMO target -- backend-demo, frontend-demo, and admin-service's
traffic-shift step -- so a demo build for a SHA with no staging success FAILS
IN THE BUILD, whichever route submitted it (bash or the admin console),
matching the plan's exit criterion 3.

Fails CLOSED, same discipline as scripts/record_build_check.py's `require`:
an inconclusive Firestore read (the query itself erroring) refuses the
deploy rather than waving it through -- an unchecked gate is not a gate.
"""

from __future__ import annotations

import argparse
import sys

from admin_backend.services.promotion_gate import staging_verified


def _client(project: str | None):
    """A Firestore client, imported lazily -- same rationale as
    scripts/record_build_check.py: a build-step runtime dependency, not a
    test dependency."""
    from google.cloud import firestore  # noqa: PLC0415

    return firestore.Client(project=project) if project else firestore.Client()


def _staging_deployments_for(target_family: str, sha: str, project: str | None):
    """The `deployments` rows Firestore actually holds for this family+sha,
    as plain dicts -- staging_verified() itself does the matching, this
    function only fetches candidates. Filtering server-side on target_family
    and sha (rather than fetching everything and filtering in python) keeps
    the read cheap regardless of how many deployment rows accumulate."""
    from google.cloud import firestore  # noqa: PLC0415

    query = (
        _client(project)
        .collection("deployments")
        .where(filter=firestore.FieldFilter("target_family", "==", target_family))
        .where(filter=firestore.FieldFilter("sha", "==", sha))
    )
    return [doc.to_dict() or {} for doc in query.stream()]


def require_staging_verified(
    target_family: str, sha: str, project: str | None
) -> int:
    try:
        deployments = _staging_deployments_for(target_family, sha, project)
    except Exception as exc:  # noqa: BLE001 -- fail CLOSED on ANY read failure
        print(
            "[promotion_gate] could not query deployments for family={} "
            "sha={}: {}".format(target_family, sha, exc),
            file=sys.stderr,
        )
        print(
            "[promotion_gate] REFUSING to deploy: the promotion gate could "
            "not be checked, and an unchecked gate is not a gate.",
            file=sys.stderr,
        )
        return 1

    if staging_verified(target_family, sha, deployments):
        print(
            "[promotion_gate] staging success found for family={} sha={} -- "
            "demo deploy allowed".format(target_family, sha)
        )
        return 0

    print(
        "[promotion_gate] no successful staging deployment found for "
        "family={} sha={} -- refusing the demo deploy. Deploy to staging "
        "first:".format(target_family, sha),
        file=sys.stderr,
    )
    print(
        "[promotion_gate]   gcloud builds submit --config=cloudbuild.yaml "
        "--substitutions=_TARGET={}-staging,_CHANNEL=staging,_SHA={}".format(
            target_family, sha
        ),
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-family", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--project", default=None)
    args = parser.parse_args(argv)
    return require_staging_verified(args.target_family, args.sha, args.project)


if __name__ == "__main__":
    raise SystemExit(main())
