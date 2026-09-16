"""The staging-before-demo promotion predicate (Epic 4 of
docs/sprint_22_admin-console_plan.md, bead polyglot-pdf-ywxoh /4.2; CONSUMED
by bead polyglot-pdf-tb3kp /4.3's POST /admin/deploys, and further extended
by bead polyglot-pdf-jub5f /4.4).

THIS MODULE WAS A PLACEHOLDER FOR 4.4 WHEN 4.2 SHIPPED IT, NOT AN EMPTY
SHELL. Bead 4.2 needed a working predicate immediately: the build-side gate
(scripts/promotion_gate.py, called from cloudbuild.yaml demo targets) has
to refuse a demo build for a SHA with no verified staging deploy, and that
refusal has to be the SAME rule every other caller enforces -- one function,
many callers, so none can drift from another. Bead 4.3's POST /admin/deploys
(admin_backend/routes/deploy_routes.py) is this module SECOND caller (the
early, friendly 409 before a build is even triggered); bead 4.4 is expected
to extend this module further (its own richer test suite), not replace it.
NOTE: an earlier version of this docstring mis-labeled 4.3 as "4.4" -- the
real 4.4 is bd polyglot-pdf-jub5f, corrected here when bd polyglot-pdf-tb3kp
became this module SECOND real consumer.

THE RULE (plan: docs/sprint_22_admin-console_plan.md, Epic 4 "Triggering and
status from the admin service"): a demo build for (target_family, sha) is
allowed only if a `deployments` record exists with channel "staging", the
SAME target_family, the SAME sha, and status "success". NO RECENCY RULE: a
newer staging deploy does NOT invalidate an older verified sha -- that is the
deliberate rollback case (redeploying an older, already-proven commit to the
demo must not be blocked just because staging has since moved on).

PURE FUNCTION, no Firestore import here. The caller (scripts/promotion_gate.py
for the build; admin_backend's route in bead 4.4) does the query and hands the
matching rows in as plain dicts, so this module is trivially unit-testable
with in-memory fixtures and carries no google-cloud-firestore dependency of
its own.

ASCII only.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

STATUS_SUCCESS = "success"
STAGING_CHANNEL = "staging"


def staging_verified(
    target_family: str,
    sha: str,
    deployments: Iterable[Mapping[str, Any]],
) -> bool:
    """True iff `deployments` contains a successful staging record for the
    exact (target_family, sha) pair.

    Args:
        target_family: the target family being promoted (e.g. "backend",
            "frontend", "admin-service" -- see scripts/record_deployment.py's
            own docstring for the family/target distinction: "backend" is the
            family shared by "backend-staging" and "backend-demo").
        sha: the commit being promoted. Compared for EXACT equality --
            promoting sha B on the strength of a staging success for sha A is
            exactly the bypass this gate exists to close.
        deployments: an iterable of deployment records (plain dicts or any
            Mapping), each expected to carry "channel", "target_family",
            "sha" and "status" keys. A record missing one of those keys is
            treated as non-matching rather than raising, since a caller may
            hand in a heterogeneous Firestore query result.

    Returns:
        True if at least one record matches channel=="staging",
        target_family==target_family, sha==sha, status=="success".
        False for an empty `deployments`, for no match, or for a match on
        every field but status (e.g. a staging build that FAILED for this
        exact sha does not count, and does not get overridden by an older
        successful staging deploy of a DIFFERENT sha -- see the no-recency
        note above: only exact-sha matches are ever considered at all).
    """
    for record in deployments:
        if (
            record.get("channel") == STAGING_CHANNEL
            and record.get("target_family") == target_family
            and record.get("sha") == sha
            and record.get("status") == STATUS_SUCCESS
        ):
            return True
    return False
