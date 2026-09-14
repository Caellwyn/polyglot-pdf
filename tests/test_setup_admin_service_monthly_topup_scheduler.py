"""scripts/setup-admin-service.sh's SECOND Cloud Scheduler declaration --
the monthly firm-plan credit top-up (bd polyglot-pdf-0euzk, plan:
"maintainer's pricing decision: 35 credits/month cap as a starting place").

Mirrors tests/test_setup_admin_service_scheduler.py's shape exactly, one job
over: an OPERATOR script that no deploy pipeline and no CI step ever
actually runs (creating the job needs the admin service's own Cloud Run
URL, unknown until after its first deploy), so the only mechanical guard is
pinning the SHIPPED SCRIPT TEXT -- the job name, schedule, HTTP method,
target path, and the two --oidc-* flags that make this job's caller
identity provable rather than merely convenient.

Deliberately does NOT invoke gcloud, and does NOT assert the scheduler
service account is ever CREATED successfully (that needs a live project) --
only that the script DECLARES creating one, and DECLARES the job with the
right shape referencing it.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-admin-service.sh"


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _job_create_block(text: str) -> str:
    """The SECOND `gcloud scheduler jobs create http ...` command's own
    lines -- the monthly top-up job, not the (first) hourly sweep job --
    from its create line through the line naming --oidc-token-audience.
    Backslash-escaped quotes (\\") are unescaped, same as test_setup_
    admin_service_scheduler.py's helper."""
    first = text.index("gcloud scheduler jobs create http")
    start = text.index("gcloud scheduler jobs create http", first + 1)
    end = text.index("--oidc-token-audience=", start)
    end = text.index("\n", end)
    return text[start:end].replace('\\"', '"')


def test_a_second_dedicated_scheduler_service_account_is_declared_and_distinct():
    """The monthly top-up job's CALLER identity must be a SEPARATE service
    account from BOTH admin-backend-sa (the callee) and the sweep job's own
    admin-sweep-scheduler-sa (a different Scheduler job's caller) -- reusing
    either would defeat the "rotating one job's credential must never
    change what a different job accepts" rule.

    Mutation: change MONTHLY_TOPUP_SCHEDULER_SA_NAME to "admin-backend-sa"
    or to "admin-sweep-scheduler-sa" -- this goes red."""
    text = _script_text()
    match = re.search(r'MONTHLY_TOPUP_SCHEDULER_SA_NAME="([^"]+)"', text)
    assert match, (
        "scripts/setup-admin-service.sh does not declare a "
        "MONTHLY_TOPUP_SCHEDULER_SA_NAME for the monthly top-up job's "
        "caller identity")
    sa_name = match.group(1)
    assert sa_name not in ("admin-backend-sa", "admin-sweep-scheduler-sa"), (
        "the monthly top-up job's caller identity must not reuse "
        "admin-backend-sa or the sweep job's own scheduler identity -- see "
        "this test's own docstring for why the identities must stay "
        "separate")
    assert (
        'gcloud iam service-accounts create "$MONTHLY_TOPUP_SCHEDULER_SA_NAME"'
        in text
    ), (
        "the declared monthly top-up scheduler service account is never "
        "actually created via `gcloud iam service-accounts create`"
    )


def test_the_job_is_declared_monthly_against_the_topup_route():
    """Mutation: change the --schedule to anything other than the plan's
    own cron string -- this goes red."""
    text = _script_text()
    job_block = _job_create_block(text)
    assert "admin-monthly-credit-topup" in job_block
    assert re.search(r'--schedule="5 0 1 \* \*"', job_block), (
        "the monthly top-up job must run on the 1st of the month, 5 "
        "minutes past midnight UTC (cron '5 0 1 * *'), matching the plan's "
        "own cron string"
    )
    assert "/admin/credits/monthly-topup" in job_block, (
        "the job's --uri must target the monthly top-up route's own path, "
        "not just the admin service's root"
    )
    assert "--http-method=POST" in job_block, (
        "the monthly top-up route is a POST route; the job must call it "
        "as one"
    )


def test_the_job_carries_both_oidc_flags_pinned_to_its_own_scheduler_sa():
    """THE SECURITY-RELEVANT HALF, mirroring test_setup_admin_service_
    scheduler.py's identical sweep-job pin. Mutation: drop
    --oidc-service-account-email -- Cloud Scheduler would then call the
    route with NO identity token at all, which require_google_oidc refuses
    (503/401), so the job would simply never work. Drop
    --oidc-token-audience -- same failure mode from the audience side."""
    text = _script_text()
    job_block = _job_create_block(text)
    assert "--oidc-service-account-email=" in job_block, (
        "the monthly top-up job must present an OIDC identity token minted "
        "by its own service account"
    )
    assert "--oidc-token-audience=" in job_block, (
        "the monthly top-up job must pin the OIDC token's audience to the "
        "route's own URL"
    )
    assert "$MONTHLY_TOPUP_SCHEDULER_SA_EMAIL" in job_block, (
        "--oidc-service-account-email must reference the DECLARED monthly "
        "top-up scheduler service account variable, not a literal or a "
        "different identity"
    )


def test_the_job_is_declared_not_executed():
    """This script must NEVER itself invoke the monthly top-up `gcloud
    scheduler jobs create` unconditionally at run time -- it can only
    appear inside an echoed NOTE block. Mutation: remove the `echo` prefix
    from the job-create line -- this goes red."""
    text = _script_text()
    first = text.index("gcloud scheduler jobs create http")
    start = text.index("gcloud scheduler jobs create http", first + 1)
    line_start = text.rfind("\n", 0, start) + 1
    line = text[line_start:start]
    assert "echo" in line, (
        "the monthly top-up `gcloud scheduler jobs create http` invocation "
        "must be inside an echoed operator NOTE, never a bare executable "
        "line"
    )


def test_the_two_scheduler_jobs_are_genuinely_distinct_declarations():
    """Sanity check tying this file to test_setup_admin_service_
    scheduler.py's own: the FIRST job block (that file's own helper) and
    the SECOND (this file's) must not be the same text -- otherwise both
    test files would silently be pinning the identical sweep job twice
    while believing they cover two different ones."""
    text = _script_text()
    first_start = text.index("gcloud scheduler jobs create http")
    second_start = text.index(
        "gcloud scheduler jobs create http", first_start + 1)
    assert first_start != second_start
    first_block = text[first_start:first_start + 60]
    second_block = text[second_start:second_start + 60]
    assert "sweep-expired-links" in first_block
    assert "monthly-credit-topup" in second_block
