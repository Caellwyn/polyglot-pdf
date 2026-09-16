"""The closed TARGETS list -- ONE constant module shared by the admin
service's deploy-trigger route and tests/test_cloudbuild_yaml.py (bd
polyglot-pdf-tb3kp, Epic 4 bead 4.3 of docs/sprint_22_admin-console_plan.md).

WHY THIS MODULE EXISTS. Before this bead, the target list existed in THREE
places that could drift: cloudbuild.yaml's substitution comment,
scripts/setup-cloud-build.sh's TARGETS array (trigger provisioning), and
tests/test_cloudbuild_yaml.py's own small per-purpose tuples (IMPLEMENTED_
TARGETS, SITE_TARGETS, etc. -- kept as-is, since each names a SUBSET for a
specific assertion, not the closed set). POST /admin/deploys
(admin_backend/routes/deploy_routes.py) needs to validate a caller-supplied
`target` string against the SAME closed set the build trigger names actually
exist for (scripts/setup-cloud-build.sh's own TARGETS array), so this module
is the one place that set is written down as DATA rather than restated a
fourth time.

TARGET vs TARGET_FAMILY vs CHANNEL. Mirrors scripts/record_deployment.py's
own vocabulary exactly (that module's docstring is the canonical explanation;
this module's target_family() is kept in sync with it BY CONVENTION, not by
import, since record_deployment.py is a build-time script and this is a
route-time constant a test also reads -- see test_target_family_matches_
record_deployment_helper in tests/test_cloudbuild_yaml.py, which asserts the
two never disagree):

  - TARGET: one entry in TARGETS, e.g. "backend-staging". What a caller
    names and what a trigger is provisioned for.
  - TARGET_FAMILY: the target with its trailing "-staging"/"-demo" suffix
    stripped, e.g. "backend". The unit the staging-before-demo promotion
    gate (admin_backend/services/promotion_gate.py) matches on: a staging
    deploy of "backend-staging" is what verifies a demo deploy of
    "backend-demo" -- same family, different target.
  - CHANNEL: which deploy/channels/<channel>.env a target's build steps
    read (staging | demo | admin). NOT always derivable from the target
    name alone (admin-service/admin-console/admin-console-candidate all
    read deploy/channels/admin.env despite carrying no "-staging"/"-demo"
    suffix), so CHANNEL_BY_TARGET is its own explicit map, not a suffix
    strip.

GATED_TARGETS is the subset the admin route's early promotion-gate check
(exit criterion 3's friendly 409) actually gates -- EXACTLY
tests/test_cloudbuild_yaml.py's own STAGING_GATED_DEMO_TARGETS, not every
"demo-channel" target: form-kits, firestore-rules
and editor all deploy to the demo channel too, but NONE has a staging
counterpart to gate against (form-kits publishes to the shared kit store,
firestore-rules is project-wide, editor has no separate staging site), so
the build carries no staging-success step for any of them and the route
must not invent one.

"admin-service" IS DELIBERATELY EXCLUDED, and this is the subtle one. The
plan gates the admin service's TRAFFIC SHIFT, and cloudbuild.yaml's own
`admin-service-staging-gate` step enforces exactly that INSIDE the build.
But the admin service has no separate staging build: the only
staging-equivalent proof for a given sha is written by that same build's
`admin-service-record-deployment` step, which by construction runs BEFORE
its own gate (the YAML says so, to avoid a bootstrap deadlock). The ROUTE's
early check queries for such a row BEFORE the build starts, so for
admin-service it can never find one for a new sha and would 409 forever --
refusing a deploy the build itself would allow. The in-build gate is the
enforcement; the route's check is only the friendly early refusal, and it
can only be friendly about targets whose proof predates the build.
GATED_TARGETS is therefore hand-listed, deliberately
NOT derived from CHANNEL_BY_TARGET == "demo" -- a channel-derived set would
silently start gating form-kits/firestore-rules/editor the moment a future
edit gave them "demo" in CHANNEL_BY_TARGET, which is not what the build
does and would refuse a deploy the build itself would allow.

"landing" IS DELIBERATELY EXCLUDED. It is named-but-not-implemented in both
cloudbuild.yaml (its "unimplemented-targets" catch-all step) and scripts/
setup-cloud-build.sh's own TARGETS array (a trigger exists so the build fails
loudly with "target not implemented" rather than "trigger not found"), but
the plan calls it out as an OPEN maintainer call ("Whether landing/ becomes a
target", Epic 4's own "Maintainer calls" section) -- the admin route's own
TARGETS allowlist is deliberately narrower than the trigger-provisioning
list, so a console user cannot trigger a build for a target the plan has not
yet decided to ship. Adding it here is a one-line change once the maintainer
decides, not a code change to the route.

ASCII only.
"""
from __future__ import annotations

# The complete set of targets a caller may request through POST
# /admin/deploys, in the SAME order scripts/setup-cloud-build.sh's own
# TARGETS array provisions triggers for (minus "landing" -- see module
# docstring). Every entry here MUST have a live "polyglot-<target>" Cloud
# Build trigger, or admin_backend/services/cloud_build.py's run_target()
# call fails at request time with a "trigger not found" error from the API
# itself -- this module does not itself verify a trigger exists (that would
# need live GCP credentials at import time), it only closes the SET of
# strings a caller may name.
TARGETS = (
    "verify",
    "backend-staging",
    "backend-demo",
    "frontend-staging",
    "frontend-demo",
    "editor",
    "form-kits",
    "firestore-rules",
    "admin-service",
    "admin-console-candidate",
    "admin-console",
)

# The deploy CHANNEL each target's build steps read their
# deploy/channels/<channel>.env from -- scripts/setup-cloud-build.sh's own
# "<target>:<channel>" TARGETS array entries, restated as a lookup a route
# can use without shelling out to that script. "verify" carries "staging" as
# a placeholder (it reads no channel env at all; the suites it runs are
# channel-independent) rather than None, so every TARGETS entry has a
# CHANNEL_BY_TARGET entry and a route need not special-case a missing key.
CHANNEL_BY_TARGET = {
    "verify": "staging",
    "backend-staging": "staging",
    "backend-demo": "demo",
    "frontend-staging": "staging",
    "frontend-demo": "demo",
    "editor": "demo",
    "form-kits": "demo",
    "firestore-rules": "demo",
    "admin-service": "admin",
    "admin-console-candidate": "admin",
    "admin-console": "admin",
}

# The channel suffixes a target name can carry -- kept identical to
# scripts/record_deployment.py's own _CHANNEL_SUFFIXES so target_family()
# below agrees with that build-time script on every TARGETS entry (pinned by
# test_target_family_matches_record_deployment_helper).
_CHANNEL_SUFFIXES = ("-staging", "-demo")


def target_family(target: str) -> str:
    """Strip a trailing channel suffix, e.g. "backend-staging" -> "backend".

    A target with neither suffix (e.g. "admin-service", "firestore-rules",
    "verify") is its own family unchanged. Mirrors scripts/
    record_deployment.py::target_family exactly -- see module docstring for
    why the two are independent copies rather than a shared import.
    """
    for suffix in _CHANNEL_SUFFIXES:
        if target.endswith(suffix):
            return target[: -len(suffix)]
    return target


# The EXACT two targets the ROUTE's early promotion-gate check applies to.
# See the module docstring's GATED_TARGETS section for why this is a
# hand-listed tuple, not a CHANNEL_BY_TARGET derivation, and for why
# "admin-service" is NOT here even though the plan gates its traffic shift.
GATED_TARGETS = ("backend-demo", "frontend-demo")
