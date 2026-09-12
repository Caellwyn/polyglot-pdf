"""Verify a Cloud Run service is PUBLICLY REACHABLE; abort if it is not.

bd polyglot-pdf-ywxoh (Epic 4 bead 4.2 of docs/sprint_22_admin-console_plan.md).
This is the ONE port of the reachability gate that used to live as FOUR
byte-identical bash copies (deploy-all.sh, backend/deploy-new.sh,
deploy-editor.sh, deploy-admin-console.sh) -- each pinned equal to the others
by tests/test_deploy_reachability_gate.py. Both the build (cloudbuild.yaml's
`admin-service` / `backend-*` targets) and the remaining bash wrappers now call
THIS module, so there is one implementation instead of a fifth hand copy for
the build and a drift risk on every future edit.

WHY THIS EXISTS AT ALL. A `gcloud run deploy --allow-unauthenticated` only
REQUESTS an allUsers -> roles/run.invoker binding; the request can be REFUSED
(the domain-restricted-sharing org policy rejects allUsers) while gcloud still
creates the service, prints a non-fatal warning, and exits 0 -- leaving a
service that 403s every request at Cloud Run's own gate, before any
application code runs. It bites only a NEW service (an existing one's binding
predates the policy and is not retroactively stripped), so the scripts and
build steps that CREATE services are exactly where this must run.

--flatten='bindings[].members' is LOAD-BEARING, same as the bash original:
  1. A raw-text grep for "allUsers" FALSE-PASSES: a `roles/run.viewer ->
     allUsers` binding satisfies it while the INVOKER binding is missing.
  2. --filter WITHOUT --flatten FALSE-FAILS: --filter runs against the WHOLE
     policy resource, and `value(bindings.role)` ';'-joins every surviving
     role onto ONE line, so an exact-line match stops matching the moment a
     service has a second binding.
--flatten makes each member/role pair its own record, so the check is
genuinely per-binding.

BOTH failure directions matter. Failing OPEN hides the bug behind a green
check; failing CLOSED blocks a good deploy. An inconclusive IAM READ (the
`gcloud` call itself erroring) therefore WARNS rather than aborting: being
unable to check is not proof of breakage.

Two entry points:
  - `verify_service_reachable(service, region, project, severity="fatal")`,
    the library function a caller (or a test) invokes directly.
  - a CLI (`python scripts/verify_service_reachable.py <service> <region>
    <project> [--severity warn|fatal]`) for cloudbuild.yaml's steps and for
    the bash wrappers, which shell out to it instead of carrying their own
    copy of the gate.

The IAM check shells out to `gcloud`. It is injected as `gcloud_runner` (a
callable taking the argv list and returning (returncode, stdout, stderr)) so
tests can stub it without a real gcloud install or network access -- the
production default calls the real binary via subprocess.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Callable

Runner = Callable[[list], "tuple[int, str, str]"]


class ServiceUnreachable(Exception):
    """Raised by verify_service_reachable() when the service is definitely
    unreachable (a fatal-severity call). Callers that want an exception
    instead of a process exit catch this; the CLI translates it to exit 1."""


def _default_gcloud_runner(argv: list) -> "tuple[int, str, str]":
    """Run gcloud for real. stdout and stderr are captured SEPARATELY --
    never merged -- so a gcloud component-update nag or deprecation notice on
    stderr can never satisfy the stdout text match below."""
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def _query_invoker_roles(
    service: str, region: str, project: str, gcloud_runner: Runner
) -> "str | None":
    """The allUsers-bound roles on `service`, one per line, or None if the
    IAM read itself failed (inconclusive)."""
    argv = [
        "gcloud",
        "run",
        "services",
        "get-iam-policy",
        service,
        "--region",
        region,
        "--project",
        project,
        "--flatten=bindings[].members",
        "--filter=bindings.members:allUsers",
        "--format=value(bindings.role)",
    ]
    rc, out, _stderr = gcloud_runner(argv)
    if rc != 0:
        return None
    return out


def verify_service_reachable(
    service: str,
    region: str,
    project: str,
    severity: str = "fatal",
    gcloud_runner: "Runner | None" = None,
    warn=print,
    error=print,
) -> bool:
    """Check that `service` has an allUsers -> roles/run.invoker binding.

    Returns True when the service is reachable OR the check was inconclusive
    (warn-and-continue). Returns False only for "warn" severity's definitive-
    unreachable case. For "fatal" severity (the default) a definitive
    unreachable result raises ServiceUnreachable instead of returning --
    mirroring the bash original's `exit 1`, which a caller cannot accidentally
    ignore by forgetting to check a return value.

    `severity` must be the literal "fatal" or "warn" -- never taken from an
    environment variable by a caller, which is the ambient-disarm trap the
    bash gate's own docstring records (an exported VERIFY_FAIL_IS_FATAL=false
    once silently downgraded the backend stage's own abort).
    """
    if severity not in ("fatal", "warn"):
        raise ValueError("severity must be 'fatal' or 'warn', got {!r}".format(severity))

    runner = gcloud_runner or _default_gcloud_runner
    invoker_roles = _query_invoker_roles(service, region, project, runner)

    if invoker_roles is None:
        warn("[WARN] Could not read the IAM policy for {} -- skipping the".format(service))
        warn("[WARN] reachability check. If the app cannot reach the backend, verify manually:")
        warn("[WARN]   gcloud run services get-iam-policy {} --region {} --project {}".format(
            service, region, project))
        return True

    if any(line.strip() == "roles/run.invoker" for line in invoker_roles.splitlines()):
        return True

    error("===========================================================")
    if severity == "warn":
        error("  WARNING: the service is NOT publicly reachable")
    else:
        error("  DEPLOY FAILED: the service is NOT publicly reachable")
    error("===========================================================")
    error("Service '{}' has no allUsers invoker binding, so".format(service))
    error("Cloud Run will 403 EVERY request before your app ever sees it.")
    error("")
    error("--allow-unauthenticated was passed, but the binding was refused --")
    error("almost always the domain-restricted-sharing org policy.")
    error("")
    error("Fix it with:")
    error("  gcloud run services add-iam-policy-binding {} \\".format(service))
    error("    --region {} --project {} \\".format(region, project))
    error("    --member=allUsers --role=roles/run.invoker")
    error("")
    error("If that is itself refused, the org policy must be relaxed for this")
    error("project first (constraints/iam.allowedPolicyMemberDomains).")
    error("See bd polyglot-pdf-pidtg.")

    if severity == "warn":
        warn("[WARN] Continuing anyway (this stage treats an unreachable backend as a warning).")
        return False

    raise ServiceUnreachable(
        "{} in {}/{} has no allUsers invoker binding".format(service, project, region)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service")
    parser.add_argument("region")
    parser.add_argument("project")
    parser.add_argument(
        "--severity",
        choices=("fatal", "warn"),
        default="fatal",
        help="fatal (default): exit 1 on a definitively unreachable service. "
        "warn: print the same message and exit 0.",
    )
    args = parser.parse_args(argv)

    def _err(msg):
        print(msg, file=sys.stderr)

    try:
        verify_service_reachable(
            args.service, args.region, args.project, args.severity, error=_err
        )
    except ServiceUnreachable:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
