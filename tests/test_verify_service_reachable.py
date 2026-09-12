"""scripts/verify_service_reachable.py -- the ONE reachability gate module
(bd polyglot-pdf-ywxoh, Epic 4 bead 4.2).

This is the python port of the bash function pinned by
tests/test_deploy_reachability_gate.py (which now asserts the four scripts
CALL this module rather than carrying their own copy). Every case that file
exercised against the bash implementation is repeated here against the real
one: reachable, unreachable (no bindings), the false-pass case (allUsers on a
non-invoker role), the false-fail case (a second binding forcing --flatten to
matter), an inconclusive IAM read (warn-and-continue), warn-mode continuing
past a definitively unreachable service, and the CLI's exit code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verify_service_reachable import (  # noqa: E402
    ServiceUnreachable,
    main,
    verify_service_reachable,
)


def _stub_runner(policy):
    """A gcloud_runner stub emulating gcloud's real --flatten projection.

    `policy` is a list of (role, member) pairs -- what the service's IAM
    policy actually contains. The stub inspects the argv it is called with
    and reproduces gcloud's real behavior for --flatten vs not, exactly like
    the bash test's driver does, so the same false-pass/false-fail regressions
    stay covered here.
    """
    flattened = "\n".join(role for role, member in policy if member == "allUsers")

    def runner(argv):
        assert "get-iam-policy" in argv
        assert any(a.startswith("--flatten") for a in argv), (
            "the query must pass --flatten, or --filter is evaluated against "
            "the whole policy resource and roles are ';'-joined onto one line"
        )
        assert any(a.startswith("--filter=bindings.members:allUsers") for a in argv)
        return 0, flattened, ""

    return runner


def _failing_runner(argv):
    return 1, "", "ERROR: (gcloud.run.services.get-iam-policy) PERMISSION_DENIED"


def test_allusers_on_invoker_passes():
    ok = verify_service_reachable(
        "svc", "us-central1", "proj",
        gcloud_runner=_stub_runner([("roles/run.invoker", "allUsers")]),
    )
    assert ok is True


def test_allusers_on_invoker_among_several_bindings_passes():
    """THE FALSE-FAIL CASE: a second binding must not defeat the exact match."""
    ok = verify_service_reachable(
        "svc", "us-central1", "proj",
        gcloud_runner=_stub_runner(
            [("roles/run.invoker", "allUsers"),
             ("roles/run.admin", "user:josh@example.com")]
        ),
    )
    assert ok is True


def test_no_bindings_at_all_raises():
    with pytest.raises(ServiceUnreachable):
        verify_service_reachable(
            "svc", "us-central1", "proj", gcloud_runner=_stub_runner([])
        )


def test_allusers_on_a_non_invoker_role_raises():
    """THE FALSE-PASS CASE: allUsers on an unrelated role must still refuse."""
    with pytest.raises(ServiceUnreachable):
        verify_service_reachable(
            "svc", "us-central1", "proj",
            gcloud_runner=_stub_runner(
                [("roles/run.viewer", "allUsers"),
                 ("roles/run.invoker", "serviceAccount:x@y.iam.gserviceaccount.com")]
            ),
        )


def test_lookalike_role_name_raises():
    """An exact match is required; a substring must not satisfy it."""
    with pytest.raises(ServiceUnreachable):
        verify_service_reachable(
            "svc", "us-central1", "proj",
            gcloud_runner=_stub_runner([("roles/run.invoker.custom", "allUsers")]),
        )


def test_failed_iam_read_warns_and_continues():
    """Being unable to CHECK is not proof of breakage -- must not raise."""
    warned = []
    ok = verify_service_reachable(
        "svc", "us-central1", "proj",
        gcloud_runner=_failing_runner,
        warn=warned.append,
    )
    assert ok is True
    assert any("skipping the" in w for w in warned)


def test_warn_mode_returns_false_instead_of_raising():
    errored = []
    ok = verify_service_reachable(
        "svc", "us-central1", "proj", severity="warn",
        gcloud_runner=_stub_runner([]),
        error=errored.append,
    )
    assert ok is False
    assert any("WARNING" in e for e in errored)
    assert not any("DEPLOY FAILED" in e for e in errored)


def test_fatal_is_the_default():
    """Omitting severity must take the fatal path, never a lenient one."""
    with pytest.raises(ServiceUnreachable):
        verify_service_reachable(
            "svc", "us-central1", "proj", gcloud_runner=_stub_runner([])
        )


def test_severity_rejects_anything_but_the_two_literals():
    """No caller can pass through an env var or a typo and get silent leniency."""
    with pytest.raises(ValueError):
        verify_service_reachable(
            "svc", "us-central1", "proj", severity="false",
            gcloud_runner=_stub_runner([("roles/run.invoker", "allUsers")]),
        )


def test_stderr_cannot_satisfy_the_check():
    """stdout and stderr must be read separately; stderr noise never counts."""
    def runner(argv):
        return 0, "", "WARNING: roles/run.invoker updates are available."

    with pytest.raises(ServiceUnreachable):
        verify_service_reachable("svc", "us-central1", "proj", gcloud_runner=runner)


def test_remedy_is_named_in_the_fatal_message():
    errored = []
    with pytest.raises(ServiceUnreachable):
        verify_service_reachable(
            "svc", "us-central1", "proj",
            gcloud_runner=_stub_runner([]),
            error=errored.append,
        )
    joined = "\n".join(errored)
    assert "add-iam-policy-binding" in joined
    assert "svc" in joined and "us-central1" in joined and "proj" in joined


# ---------------------------------------------------------------------------
# The CLI (what cloudbuild.yaml's steps and the bash wrappers actually call).
# ---------------------------------------------------------------------------


def test_cli_exit_code_is_zero_when_reachable(monkeypatch):
    import verify_service_reachable as mod

    monkeypatch.setattr(
        mod, "_default_gcloud_runner",
        lambda argv: (0, "roles/run.invoker", ""),
    )
    assert main(["svc", "us-central1", "proj"]) == 0


def test_cli_exit_code_is_one_when_unreachable(monkeypatch, capsys):
    import verify_service_reachable as mod

    monkeypatch.setattr(mod, "_default_gcloud_runner", lambda argv: (0, "", ""))
    assert main(["svc", "us-central1", "proj"]) == 1
    captured = capsys.readouterr()
    assert "DEPLOY FAILED" in captured.err


def test_cli_warn_flag_exits_zero_over_an_unreachable_service(monkeypatch, capsys):
    import verify_service_reachable as mod

    monkeypatch.setattr(mod, "_default_gcloud_runner", lambda argv: (0, "", ""))
    assert main(["svc", "us-central1", "proj", "--severity", "warn"]) == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


def test_cli_rejects_an_unknown_severity():
    with pytest.raises(SystemExit):
        main(["svc", "us-central1", "proj", "--severity", "maybe"])
