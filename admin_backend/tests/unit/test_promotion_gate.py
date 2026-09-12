"""admin_backend.services.promotion_gate.staging_verified -- the staging-
before-demo predicate (bd polyglot-pdf-ywxoh, Epic 4 bead 4.2; extended by
bead polyglot-pdf-tb3kp / 4.4).

Plan rule (docs/sprint_22_admin-console_plan.md, Epic 4): a demo build for
(target_family, sha) is allowed only if `deployments` has a record with
channel=="staging", the SAME target_family, the SAME sha, status=="success".
No recency rule -- a newer staging deploy must not invalidate an older
verified sha (the rollback case).
"""
from __future__ import annotations

from admin_backend.services.promotion_gate import staging_verified


def _record(**overrides):
    base = {
        "channel": "staging",
        "target_family": "backend",
        "sha": "abc123",
        "status": "success",
    }
    base.update(overrides)
    return base


def test_matching_success_record_verifies():
    assert staging_verified("backend", "abc123", [_record()]) is True


def test_no_records_at_all_is_unverified():
    assert staging_verified("backend", "abc123", []) is False


def test_wrong_channel_does_not_verify():
    """A demo record for the same sha/family must not satisfy this -- the
    whole point is that a demo build cannot vouch for itself."""
    assert staging_verified(
        "backend", "abc123", [_record(channel="demo")]
    ) is False


def test_wrong_target_family_does_not_verify():
    """A staging success for FRONTEND must not clear a BACKEND demo build."""
    assert staging_verified(
        "backend", "abc123", [_record(target_family="frontend")]
    ) is False


def test_wrong_sha_does_not_verify():
    """A staging success for a DIFFERENT commit must not clear this one."""
    assert staging_verified(
        "backend", "abc123", [_record(sha="def456")]
    ) is False


def test_failed_staging_record_for_the_exact_sha_does_not_verify():
    assert staging_verified(
        "backend", "abc123", [_record(status="failure")]
    ) is False


def test_working_or_queued_status_does_not_verify():
    for status in ("working", "queued", "cancelled"):
        assert staging_verified(
            "backend", "abc123", [_record(status=status)]
        ) is False, status


def test_a_record_missing_expected_keys_does_not_raise_or_match():
    assert staging_verified("backend", "abc123", [{}]) is False


def test_no_recency_rule_an_older_verified_sha_still_verifies():
    """THE ROLLBACK CASE. Staging has since moved on to a NEWER sha, but the
    OLDER sha's own staging success record still stands -- it is not
    invalidated by a later, unrelated staging deploy. Promoting that older,
    already-proven sha to the demo (a rollback) must still be allowed."""
    records = [
        _record(sha="old-sha"),
        _record(sha="new-sha"),
    ]
    assert staging_verified("backend", "old-sha", records) is True


def test_multiple_records_one_matching_among_several_non_matching():
    records = [
        _record(channel="demo"),
        _record(target_family="frontend"),
        _record(status="failure"),
        _record(),  # the one real match
    ]
    assert staging_verified("backend", "abc123", records) is True


def test_both_directions_through_one_case():
    """Exit criterion phrasing: 'proves the predicate both ways'. A single
    fixture set exercised for both the allow and the refuse outcome."""
    records = [_record(target_family="backend", sha="s1", status="success")]
    assert staging_verified("backend", "s1", records) is True
    assert staging_verified("backend", "s2", records) is False
