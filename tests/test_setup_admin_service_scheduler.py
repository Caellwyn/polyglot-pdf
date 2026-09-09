"""scripts/setup-admin-service.sh's Cloud Scheduler declaration (Epic 2
bead B5, plan: "Refund on unopened expiry").

Mirrors test_setup_firestore_ttl_script.py's shape: an OPERATOR script that
no deploy pipeline and no CI step ever actually runs (creating the job needs
the admin service's own Cloud Run URL, unknown until after its first
deploy), so the only mechanical guard is pinning the SHIPPED SCRIPT TEXT --
the job name, schedule, HTTP method, target path, and the two --oidc-* flags
that make this job's caller identity provable rather than merely
convenient.

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
    """The `gcloud scheduler jobs create http ...` command's own lines
    (each an independent `echo` statement in the shipped script, not a
    single shell-continued command -- see test_the_job_is_declared_not_
    executed's own note on why), from the create line through the line
    naming --oidc-token-audience, so flag assertions below are scoped to
    the REAL command and not to a NOTE line elsewhere that happens to
    mention one of the same flag names in prose.

    Backslash-escaped quotes (\\") are UNESCAPED before returning: the
    script's own `echo -e "...\\"..."` quoting is a detail of how it PRINTS
    the command, not part of the gcloud invocation a copy-paste would
    actually run, and tests here assert against the semantic command.
    """
    start = text.index("gcloud scheduler jobs create http")
    end = text.index("--oidc-token-audience=", start)
    end = text.index("\n", end)
    return text[start:end].replace('\\"', '"')


def test_cloudscheduler_api_is_enabled():
    """Mutation: remove cloudscheduler.googleapis.com from the `gcloud
    services enable` block -- this goes red."""
    text = _script_text()
    match = re.search(
        r"gcloud services enable\s*\\((?:\s*[a-z.]+\.googleapis\.com\s*\\?\n?)+\))?",
        text)
    # The enable block spans multiple backslash-continued lines; simplest
    # robust check is substring search within the block bounded by the next
    # blank line after the `gcloud services enable` invocation.
    start = text.index("gcloud services enable")
    end = text.index("\n\n", start)
    enable_block = text[start:end]
    assert "cloudscheduler.googleapis.com" in enable_block, (
        "scripts/setup-admin-service.sh must enable "
        "cloudscheduler.googleapis.com -- the sweep job (bd "
        "polyglot-pdf-8vgfh) needs it, and an API enabled ahead of its "
        "first consumer is the same unused-surface risk as an unused IAM "
        "grant (this script's own docstring rule).")


def test_a_dedicated_scheduler_service_account_is_declared_and_it_is_not_the_admin_sa():
    """The scheduler's CALLER identity must be a SEPARATE service account
    from admin-backend-sa (the admin service's own, CALLEE identity) --
    reusing one identity for both directions would defeat require_google_
    oidc's whole reason to pin a caller email distinct from mere audience
    matching. Mutation: change SCHEDULER_SA_NAME to "admin-backend-sa" --
    this goes red."""
    text = _script_text()
    match = re.search(r'SCHEDULER_SA_NAME="([^"]+)"', text)
    assert match, (
        "scripts/setup-admin-service.sh does not declare a "
        "SCHEDULER_SA_NAME for the Cloud Scheduler job's caller identity")
    scheduler_sa_name = match.group(1)
    assert scheduler_sa_name != "admin-backend-sa", (
        "the scheduler job's caller identity must NOT be admin-backend-sa "
        "(the admin service's own identity) -- see this test's own "
        "docstring for why the two must stay separate")
    assert "gcloud iam service-accounts create \"$SCHEDULER_SA_NAME\"" in text \
        or "gcloud iam service-accounts create \"${SCHEDULER_SA_NAME}\"" in text, (
        "the declared scheduler service account is never actually created "
        "via `gcloud iam service-accounts create`")


def test_the_job_is_declared_hourly_against_the_sweep_route():
    """Mutation: change the --schedule to anything other than an hourly
    cron expression -- this goes red (the plan says 'an hourly sweep')."""
    text = _script_text()
    job_block = _job_create_block(text)
    assert "admin-sweep-expired-links" in job_block
    assert re.search(r'--schedule="0 \* \* \* \*"', job_block), (
        "the scheduler job must run hourly on the hour (cron '0 * * * *'), "
        "matching the plan's 'an hourly sweep'"
    )
    assert "/admin/links/sweep-expired" in job_block, (
        "the job's --uri must target the sweep route's own path, not just "
        "the admin service's root"
    )
    assert "--http-method=POST" in job_block, (
        "the sweep route is a POST route; the job must call it as one"
    )


def test_the_job_carries_both_oidc_flags_pinned_to_the_scheduler_sa():
    """THE SECURITY-RELEVANT HALF. Mutation: drop --oidc-service-account-
    email -- Cloud Scheduler would then call the route with NO identity
    token at all, which require_google_oidc refuses (401), so the job would
    simply never work -- but a reviewer scanning this script's TEXT should
    catch that before a deploy does. Drop --oidc-token-audience -- same
    failure mode from the audience side."""
    text = _script_text()
    job_block = _job_create_block(text)
    assert "--oidc-service-account-email=" in job_block, (
        "the scheduler job must present an OIDC identity token minted by "
        "its own service account -- without --oidc-service-account-email "
        "Cloud Scheduler sends no Authorization header at all"
    )
    assert "--oidc-token-audience=" in job_block, (
        "the scheduler job must pin the OIDC token's audience to the "
        "sweep route's own URL"
    )
    # The declared scheduler SA (not admin-backend-sa) is what mints the
    # token -- pin the REFERENCE, not just the flag's presence.
    assert "$SCHEDULER_SA_EMAIL" in job_block, (
        "--oidc-service-account-email must reference the DECLARED "
        "scheduler service account variable, not a literal or a different "
        "identity"
    )


def test_the_job_is_declared_not_executed():
    """This script must NEVER itself invoke `gcloud scheduler jobs create`
    unconditionally at run time -- it can only appear inside an echoed NOTE
    block (an operator command to copy-paste), never as a bare executable
    line. Mutation: remove the `echo` prefix from the job-create line,
    making it an EXECUTABLE gcloud invocation -- this goes red."""
    text = _script_text()
    start = text.index("gcloud scheduler jobs create http")
    # Walk backward to the start of that physical line.
    line_start = text.rfind("\n", 0, start) + 1
    line = text[line_start:start]
    assert "echo" in line, (
        "the `gcloud scheduler jobs create http` invocation must be inside "
        "an echoed operator NOTE, never a bare executable line -- this "
        "script declares the job, it does not create it (the admin "
        "service's URL does not exist until after its first deploy)"
    )
