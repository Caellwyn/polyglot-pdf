"""deploy-admin.sh must re-assert ADMIN_SERVICE_URL / SWEEP_SCHEDULER_SA_EMAIL
on EVERY run, not rely on a one-time hand-run step (bd polyglot-pdf-8vgfh
cross-surface review finding 3).

WHY THIS EXISTS. deploy-all.sh's backend stage deploys with `--set-env-vars`,
which REPLACES the Cloud Run service's ENTIRE env block (see that flag's own
usage and the neighboring --set-secrets comment in deploy-all.sh, which makes
exactly this point). scripts/setup-admin-service.sh used to instruct an
operator to set ADMIN_SERVICE_URL and SWEEP_SCHEDULER_SA_EMAIL by hand, ONCE,
via a separate `gcloud run services update ... --update-env-vars` -- a value
that the very next `./deploy-admin.sh` run then silently wiped, fail-closing
the sweep route (503) with no test or alert able to notice.

The fix folds both values into deploy-admin.sh's OWN BACKEND_EXTRA_ENV, so
every deploy re-asserts them as part of that same --set-env-vars call instead
of depending on a separate, erasable step.

WHY THIS IS STATIC-TEXT ASSERTION, NOT AN EXECUTED SHELL DRIVE (unlike
test_deploy_admin_tag_flow.py, which stubs gcloud/curl/git and runs the
extracted backend-stage block). The logic under test here is a short,
straight-line set of assignments near the top of deploy-admin.sh, not a
conditional flow whose branches matter -- a text-shape assertion is enough
to pin "the value is computed and appended to BACKEND_EXTRA_ENV before the
deploy-all.sh call", and mirrors test_deploy_admin_cors_origins.py's own
DERIVED-FROM-THE-SCRIPT approach for the same file.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ADMIN = REPO_ROOT / "deploy-admin.sh"
DEPLOY_ALL = REPO_ROOT / "deploy-all.sh"
SETUP_ADMIN_SERVICE = REPO_ROOT / "scripts" / "setup-admin-service.sh"


def _live_text(path: Path) -> str:
    """Strip full-line `#` comments so a commented-out assignment can't be
    parsed as the real one (mirrors test_deploy_admin_cors_origins.py's own
    helper of the same name, for the same file)."""
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    ]
    return "\n".join(lines)


def test_deploy_all_set_env_vars_replaces_the_whole_env_block():
    """Sanity-check on the premise this whole file exists to guard: if
    deploy-all.sh ever stopped using --set-env-vars (replace-the-whole-block
    semantics) for the backend deploy -- e.g. switched to --update-env-vars
    (merge semantics) -- the wipe this test guards against would no longer
    happen, and this file's fix would be unnecessary (though harmless)."""
    text = _live_text(DEPLOY_ALL)
    assert '--set-env-vars="$BACKEND_ENV"' in text, (
        "deploy-all.sh's backend deploy no longer uses --set-env-vars -- if "
        "it now merges env vars instead of replacing them, re-derive "
        "whether this file's fix (folding ADMIN_SERVICE_URL and "
        "SWEEP_SCHEDULER_SA_EMAIL into deploy-admin.sh's own "
        "BACKEND_EXTRA_ENV) is still needed, do not just delete this test")


def test_admin_service_url_is_computed_before_the_deploy_all_call():
    """deploy-admin.sh must look up ADMIN_SERVICE_URL (via `gcloud run
    services describe`) BEFORE its ./deploy-all.sh call, not only after (the
    existing post-deploy ADMIN_URL lookup, used only for the printed
    summary, does not feed the deploy's own env vars). Mutation: delete the
    pre-deploy ADMIN_SERVICE_URL assignment -- this goes red."""
    text = _live_text(DEPLOY_ADMIN)
    deploy_all_call = text.index("./deploy-all.sh --backend")
    before_deploy = text[:deploy_all_call]
    assert re.search(
        r'ADMIN_SERVICE_URL=\$\(gcloud run services describe',
        before_deploy), (
        "deploy-admin.sh must compute ADMIN_SERVICE_URL via `gcloud run "
        "services describe` BEFORE calling ./deploy-all.sh, so this same "
        "deploy's env vars can carry it forward -- found no such assignment "
        "ahead of the deploy-all.sh call")
    # Must tolerate the not-yet-deployed-service case (the true first
    # deploy) rather than aborting under `set -e`.
    assert re.search(
        r'ADMIN_SERVICE_URL=\$\(gcloud run services describe[^\n]*\n'
        r'(?:[^\n]*\n)*?[^\n]*2>/dev/null \|\| true\)',
        before_deploy), (
        "the pre-deploy ADMIN_SERVICE_URL lookup must swallow a "
        "not-yet-existing service (2>/dev/null || true) rather than "
        "aborting the whole script under `set -e` on a service's true "
        "first deploy")


def test_sweep_scheduler_sa_email_is_computed_without_a_gcloud_lookup():
    """SWEEP_SCHEDULER_SA_EMAIL must be constructible from the fixed
    SCHEDULER_SA_NAME literal ("admin-sweep-scheduler-sa") declared in
    scripts/setup-admin-service.sh, not looked up -- unlike
    ADMIN_SERVICE_URL, this value is known before the service's first
    deploy. Mutation: delete the SWEEP_SCHEDULER_SA_EMAIL assignment in
    deploy-admin.sh -- this goes red."""
    deploy_admin_text = _live_text(DEPLOY_ADMIN)
    match = re.search(
        r'SWEEP_SCHEDULER_SA_EMAIL="([^"]+)"', deploy_admin_text)
    assert match, (
        "deploy-admin.sh does not declare SWEEP_SCHEDULER_SA_EMAIL")
    assert match.group(1) == "admin-sweep-scheduler-sa@$PROJECT.iam.gserviceaccount.com", (
        "SWEEP_SCHEDULER_SA_EMAIL in deploy-admin.sh does not match the "
        "scheduler SA name literal declared in scripts/setup-admin-"
        "service.sh -- got {!r}".format(match.group(1)))

    setup_text = _live_text(SETUP_ADMIN_SERVICE)
    sa_name_match = re.search(r'SCHEDULER_SA_NAME="([^"]+)"', setup_text)
    assert sa_name_match, (
        "scripts/setup-admin-service.sh no longer declares "
        "SCHEDULER_SA_NAME -- deploy-admin.sh's hard-coded "
        "'admin-sweep-scheduler-sa' literal needs re-deriving against "
        "whatever replaced it")
    assert sa_name_match.group(1) in match.group(1), (
        "deploy-admin.sh's SWEEP_SCHEDULER_SA_EMAIL ({!r}) does not embed "
        "scripts/setup-admin-service.sh's actual SCHEDULER_SA_NAME "
        "({!r}) -- the two would silently name different service "
        "accounts".format(match.group(1), sa_name_match.group(1)))


def test_both_sweep_env_vars_reach_backend_extra_env():
    """THE SET GUARD. Both ADMIN_SERVICE_URL and SWEEP_SCHEDULER_SA_EMAIL
    must actually reach the BACKEND_EXTRA_ENV passed to ./deploy-all.sh --
    computing them and never using them would be exactly as broken as not
    computing them at all. Mutation: compute SWEEP_ENV but drop
    ",$SWEEP_ENV" from the BACKEND_EXTRA_ENV assignment -- this goes red."""
    text = _live_text(DEPLOY_ADMIN)
    deploy_all_call = text.index("./deploy-all.sh --backend")
    before_deploy = text[:deploy_all_call]

    extra_env_match = re.search(
        r'BACKEND_EXTRA_ENV="([^"]*)"', before_deploy)
    assert extra_env_match, (
        "no BACKEND_EXTRA_ENV assignment found before the ./deploy-all.sh "
        "call in deploy-admin.sh")
    extra_env_value = extra_env_match.group(1)

    # The two sweep env vars may be assembled into an intermediate variable
    # (e.g. SWEEP_ENV, possibly reassigned across more than one statement --
    # `[ -n "$ADMIN_SERVICE_URL" ] && SWEEP_ENV="$SWEEP_ENV,..."` is a
    # conditional APPEND, not a single literal) rather than typed inline --
    # so resolve every bare $VARNAME reference inside BACKEND_EXTRA_ENV's own
    # value against EVERY assignment to that name found anywhere earlier in
    # the script (not just the first), exactly like the reconcile_expired_
    # for_firm-style "read the real value" guards elsewhere in this repo's
    # test suite.
    referenced_vars = re.findall(r'\$([A-Za-z_][A-Za-z0-9_]*)', extra_env_value)
    resolved = extra_env_value
    for var_name in referenced_vars:
        for var_match in re.finditer(
                r'{}="([^"]*)"'.format(re.escape(var_name)), before_deploy):
            resolved += " " + var_match.group(1)

    assert "ADMIN_SERVICE_URL" in resolved, (
        "deploy-admin.sh computes ADMIN_SERVICE_URL but never folds it "
        "into BACKEND_EXTRA_ENV (directly, or via a referenced "
        "intermediate variable) -- the sweep route's audience gate would "
        "still fail-closed (503) on every deploy after the first")
    assert "SWEEP_SCHEDULER_SA_EMAIL" in resolved, (
        "deploy-admin.sh computes SWEEP_SCHEDULER_SA_EMAIL but never folds "
        "it into BACKEND_EXTRA_ENV (directly, or via a referenced "
        "intermediate variable) -- the sweep route's allowlist gate would "
        "still fail-closed (503) on every deploy")


def test_setup_admin_service_no_longer_instructs_a_bare_self_assignment_note():
    """scripts/setup-admin-service.sh must not tell an operator to
    hand-apply these two values via a bare NOTE like
    'ADMIN_SERVICE_URL=$ADMIN_SERVICE_URL' any more -- that instruction was
    exactly the erasable step this fix replaces (the next deploy-admin.sh
    run's --set-env-vars call would wipe whatever the operator hand-applied
    from it). Mutation: reintroduce that literal printed NOTE line -- this
    goes red. (Explanatory prose that MENTIONS the old flow, to tell an
    operator it no longer applies, is fine and is not what this guards.)"""
    text = SETUP_ADMIN_SERVICE.read_text(encoding="utf-8")
    assert "ADMIN_SERVICE_URL=\\$ADMIN_SERVICE_URL" not in text, (
        "scripts/setup-admin-service.sh still prints the old bare "
        "'ADMIN_SERVICE_URL=$ADMIN_SERVICE_URL' self-assignment NOTE -- "
        "these values are now set automatically by deploy-admin.sh on "
        "every run (bd polyglot-pdf-8vgfh finding 3); a hand-applied value "
        "that a later deploy silently wipes is the bug that was fixed")
    assert "gcloud run services update" not in text, (
        "scripts/setup-admin-service.sh still instructs a separate "
        "`gcloud run services update` step for these env vars -- that "
        "step's effect is silently wiped by the next deploy-admin.sh run's "
        "--set-env-vars call (which REPLACES the whole env block); fold "
        "the value into deploy-admin.sh's own BACKEND_EXTRA_ENV instead")


def test_monthly_topup_scheduler_sa_email_is_computed_without_a_gcloud_lookup():
    """MONTHLY_TOPUP_SCHEDULER_SA_EMAIL (bd polyglot-pdf-0euzk) must be
    constructible from the fixed MONTHLY_TOPUP_SCHEDULER_SA_NAME literal
    declared in scripts/setup-admin-service.sh, mirroring
    test_sweep_scheduler_sa_email_is_computed_without_a_gcloud_lookup's own
    check one env var over. Mutation: delete the
    MONTHLY_TOPUP_SCHEDULER_SA_EMAIL assignment in deploy-admin.sh -- this
    goes red."""
    deploy_admin_text = _live_text(DEPLOY_ADMIN)
    match = re.search(
        r'MONTHLY_TOPUP_SCHEDULER_SA_EMAIL="([^"]+)"', deploy_admin_text)
    assert match, (
        "deploy-admin.sh does not declare MONTHLY_TOPUP_SCHEDULER_SA_EMAIL")
    assert match.group(1) == (
        "admin-topup-scheduler-sa@$PROJECT.iam.gserviceaccount.com"
    ), (
        "MONTHLY_TOPUP_SCHEDULER_SA_EMAIL in deploy-admin.sh does not match "
        "the scheduler SA name literal declared in scripts/setup-admin-"
        "service.sh -- got {!r}".format(match.group(1)))

    setup_text = _live_text(SETUP_ADMIN_SERVICE)
    sa_name_match = re.search(
        r'MONTHLY_TOPUP_SCHEDULER_SA_NAME="([^"]+)"', setup_text)
    assert sa_name_match, (
        "scripts/setup-admin-service.sh no longer declares "
        "MONTHLY_TOPUP_SCHEDULER_SA_NAME -- deploy-admin.sh's hard-coded "
        "literal needs re-deriving against whatever replaced it")
    assert sa_name_match.group(1) in match.group(1), (
        "deploy-admin.sh's MONTHLY_TOPUP_SCHEDULER_SA_EMAIL ({!r}) does "
        "not embed scripts/setup-admin-service.sh's actual "
        "MONTHLY_TOPUP_SCHEDULER_SA_NAME ({!r}) -- the two would silently "
        "name different service accounts".format(
            match.group(1), sa_name_match.group(1)))


def test_monthly_topup_scheduler_sa_email_reaches_backend_extra_env():
    """THE SET GUARD, one env var over from test_both_sweep_env_vars_
    reach_backend_extra_env: MONTHLY_TOPUP_SCHEDULER_SA_EMAIL must actually
    reach the BACKEND_EXTRA_ENV passed to ./deploy-all.sh -- computing it
    and never using it is exactly as broken as not computing it at all.
    Mutation: compute the value but drop it from the SWEEP_ENV
    concatenation -- this goes red."""
    text = _live_text(DEPLOY_ADMIN)
    deploy_all_call = text.index("./deploy-all.sh --backend")
    before_deploy = text[:deploy_all_call]

    extra_env_match = re.search(
        r'BACKEND_EXTRA_ENV="([^"]*)"', before_deploy)
    assert extra_env_match, (
        "no BACKEND_EXTRA_ENV assignment found before the ./deploy-all.sh "
        "call in deploy-admin.sh")
    extra_env_value = extra_env_match.group(1)

    referenced_vars = re.findall(r'\$([A-Za-z_][A-Za-z0-9_]*)', extra_env_value)
    resolved = extra_env_value
    for var_name in referenced_vars:
        for var_match in re.finditer(
                r'{}="([^"]*)"'.format(re.escape(var_name)), before_deploy):
            resolved += " " + var_match.group(1)

    assert "MONTHLY_TOPUP_SCHEDULER_SA_EMAIL" in resolved, (
        "deploy-admin.sh computes MONTHLY_TOPUP_SCHEDULER_SA_EMAIL but "
        "never folds it into BACKEND_EXTRA_ENV (directly, or via a "
        "referenced intermediate variable) -- the monthly top-up route's "
        "allowlist gate would fail-closed (503) on every deploy")


def test_pubsub_push_sa_email_is_computed_without_a_gcloud_lookup():
    """PUBSUB_PUSH_SA_EMAIL (bd polyglot-pdf-tb3kp, E4.3's Cloud Build
    build-status webhook OIDC gate) must be constructible from the fixed
    PUBSUB_PUSH_SA_NAME literal ("admin-pubsub-push-sa") declared in
    scripts/setup-admin-service.sh, mirroring
    test_sweep_scheduler_sa_email_is_computed_without_a_gcloud_lookup's own
    check. Fresh-eyes/cross-surface review finding: this var was set by NO
    deploy path -- only printed as a one-time hand-run NOTE -- so
    require_google_oidc's caller allowlist resolved to empty on every real
    deploy, permanently fail-closing POST /api/deploys/webhook. Mutation:
    delete the PUBSUB_PUSH_SA_EMAIL assignment in deploy-admin.sh -- this
    goes red."""
    deploy_admin_text = _live_text(DEPLOY_ADMIN)
    match = re.search(
        r'PUBSUB_PUSH_SA_EMAIL="([^"]+)"', deploy_admin_text)
    assert match, (
        "deploy-admin.sh does not declare PUBSUB_PUSH_SA_EMAIL")
    assert match.group(1) == (
        "admin-pubsub-push-sa@$PROJECT.iam.gserviceaccount.com"
    ), (
        "PUBSUB_PUSH_SA_EMAIL in deploy-admin.sh does not match the "
        "scheduler SA name literal declared in scripts/setup-admin-"
        "service.sh -- got {!r}".format(match.group(1)))

    setup_text = _live_text(SETUP_ADMIN_SERVICE)
    sa_name_match = re.search(r'PUBSUB_PUSH_SA_NAME="([^"]+)"', setup_text)
    assert sa_name_match, (
        "scripts/setup-admin-service.sh no longer declares "
        "PUBSUB_PUSH_SA_NAME -- deploy-admin.sh's hard-coded "
        "'admin-pubsub-push-sa' literal needs re-deriving against "
        "whatever replaced it")
    assert sa_name_match.group(1) in match.group(1), (
        "deploy-admin.sh's PUBSUB_PUSH_SA_EMAIL ({!r}) does not embed "
        "scripts/setup-admin-service.sh's actual PUBSUB_PUSH_SA_NAME "
        "({!r}) -- the two would silently name different service "
        "accounts".format(match.group(1), sa_name_match.group(1)))


def test_pubsub_push_sa_email_reaches_backend_extra_env():
    """THE SET GUARD, one env var over from test_both_sweep_env_vars_
    reach_backend_extra_env: PUBSUB_PUSH_SA_EMAIL must actually reach the
    BACKEND_EXTRA_ENV passed to ./deploy-all.sh -- computing it and never
    using it is exactly as broken as not computing it at all. Mutation:
    compute the value but drop it from the SWEEP_ENV concatenation -- this
    goes red."""
    text = _live_text(DEPLOY_ADMIN)
    deploy_all_call = text.index("./deploy-all.sh --backend")
    before_deploy = text[:deploy_all_call]

    extra_env_match = re.search(
        r'BACKEND_EXTRA_ENV="([^"]*)"', before_deploy)
    assert extra_env_match, (
        "no BACKEND_EXTRA_ENV assignment found before the ./deploy-all.sh "
        "call in deploy-admin.sh")
    extra_env_value = extra_env_match.group(1)

    referenced_vars = re.findall(r'\$([A-Za-z_][A-Za-z0-9_]*)', extra_env_value)
    resolved = extra_env_value
    for var_name in referenced_vars:
        for var_match in re.finditer(
                r'{}="([^"]*)"'.format(re.escape(var_name)), before_deploy):
            resolved += " " + var_match.group(1)

    assert "PUBSUB_PUSH_SA_EMAIL" in resolved, (
        "deploy-admin.sh computes PUBSUB_PUSH_SA_EMAIL but never folds it "
        "into BACKEND_EXTRA_ENV (directly, or via a referenced "
        "intermediate variable) -- the Cloud Build webhook's OIDC "
        "allowlist gate would stay permanently fail-closed on every deploy")
