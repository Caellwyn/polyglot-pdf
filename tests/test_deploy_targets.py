"""Dedicated unit coverage for deploy/targets.py's own logic (bd
polyglot-pdf-tb3kp, Epic 4 bead 4.3 of docs/sprint_22_admin-console_plan.md).

WHY THIS FILE EXISTS. deploy/targets.py's module docstring pointed at a
cross-check test (test_target_family_matches_record_deployment_helper in
tests/test_cloudbuild_yaml.py, now real) as its drift guard against
scripts/record_deployment.py's independent copy of target_family() -- but
that cross-check only proves the two copies AGREE, never that
deploy/targets.py's own internal invariants hold. This module is the sole
gate POST /admin/deploys (admin_backend/routes/deploy_routes.py) uses to
validate a caller-supplied target, so its constants and target_family()
get their own direct assertions here (CLAUDE.md scar #8: enumerate the set,
then pin the set -- a fabricated-looking safety claim in a security-
relevant module is worse than none, per the fresh-eyes review that flagged
this gap).

ASCII only.
"""

from __future__ import annotations

from deploy.targets import (
    CHANNEL_BY_TARGET,
    GATED_TARGETS,
    TARGETS,
    target_family,
)


def test_every_target_has_a_channel():
    """CHANNEL_BY_TARGET must cover every TARGETS entry -- deploy_routes.py
    reads it with a plain [] lookup, so a missing key would be a KeyError
    at request time rather than a clean validation error."""
    missing = [t for t in TARGETS if t not in CHANNEL_BY_TARGET]
    assert not missing, (
        "TARGETS entries with no CHANNEL_BY_TARGET mapping: {}".format(
            missing
        )
    )


def test_channel_by_target_has_no_extra_keys():
    """CHANNEL_BY_TARGET must not name a target outside the closed
    TARGETS set -- an extra key here would be dead data nothing validates
    against, and a typo'd key would silently never be looked up."""
    extra = [t for t in CHANNEL_BY_TARGET if t not in TARGETS]
    assert not extra, (
        "CHANNEL_BY_TARGET keys not present in TARGETS: {}".format(extra)
    )


def test_targets_has_no_duplicates():
    assert len(TARGETS) == len(set(TARGETS)), (
        "TARGETS contains duplicate entries: {}".format(TARGETS)
    )


def test_landing_is_not_a_target():
    """Module docstring's own "landing IS DELIBERATELY EXCLUDED" section --
    pinned here so a future edit that adds it back does so on purpose, not
    by accident (the plan calls this an open maintainer decision)."""
    assert "landing" not in TARGETS


def test_gated_targets_is_a_subset_of_targets():
    missing = [t for t in GATED_TARGETS if t not in TARGETS]
    assert not missing, (
        "GATED_TARGETS names targets not in TARGETS: {}".format(missing)
    )


def test_gated_targets_is_exactly_the_two_with_a_pre_build_staging_proof():
    """GATED_TARGETS is hand-listed, deliberately NOT derived from
    CHANNEL_BY_TARGET == "demo" (module docstring's own rationale: several
    demo-channel targets have no staging counterpart to gate against). Pin
    the exact set so a future edit cannot silently widen or narrow it."""
    assert set(GATED_TARGETS) == {"backend-demo", "frontend-demo"}


def test_admin_service_is_not_route_gated():
    """admin-service's staging proof is written INSIDE its own build (see the
    module docstring), so a route-level pre-check could never find one and
    would 409 every admin-service deploy forever. The in-build
    admin-service-staging-gate step is what enforces the plan's rule."""
    assert "admin-service" in TARGETS
    assert "admin-service" not in GATED_TARGETS


def test_target_family_strips_known_suffixes():
    assert target_family("backend-staging") == "backend"
    assert target_family("backend-demo") == "backend"
    assert target_family("frontend-staging") == "frontend"
    assert target_family("frontend-demo") == "frontend"


def test_target_family_is_identity_for_unsuffixed_targets():
    assert target_family("admin-service") == "admin-service"
    assert target_family("firestore-rules") == "firestore-rules"
    assert target_family("verify") == "verify"
    assert target_family("editor") == "editor"
    assert target_family("form-kits") == "form-kits"
    assert target_family("admin-console") == "admin-console"
    assert target_family("admin-console-candidate") == "admin-console-candidate"


def test_target_family_covers_every_target_without_crashing():
    """Enumerated, not hand-picked (CLAUDE.md scar #8) -- every TARGETS
    entry must resolve to a non-empty family string."""
    for t in TARGETS:
        family = target_family(t)
        assert family, "target_family({!r}) returned falsy: {!r}".format(
            t, family
        )
