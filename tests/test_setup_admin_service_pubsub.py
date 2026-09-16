"""scripts/setup-admin-service.sh's Pub/Sub build-status webhook wiring (bd
polyglot-pdf-tb3kp, Epic 4 bead 4.3 of docs/sprint_22_admin-console_plan.md).

Mirrors test_setup_admin_service_scheduler.py's shape: an OPERATOR script
whose push-subscription creation needs the admin service's OWN Cloud Run
URL (unknown until after its first deploy), so the subscription-create
command is a printed NOTE, not an executed one -- the only mechanical guard
is pinning the SHIPPED SCRIPT TEXT (the API enable, the topic, the dedicated
push-caller service account, and the NOTE's own --push-auth-* flags).

roles/iam.serviceAccountTokenCreator for the Pub/Sub SERVICE AGENT is
pinned by admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py's
test_pubsub_service_agent_gets_token_creator_for_the_build_webhook, which
reads scripts/setup-cloud-build.sh (bead polyglot-pdf-p4ale, E4.5) -- NOT
this file, and NOT setup-admin-service.sh. This file only covers what THIS
script declares: the API enable, the topic, and the push SUBSCRIPTION's own
caller identity (a THIRD account, distinct from both admin-backend-sa and
polyglot-cloudbuild-sa).

ASCII only.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-admin-service.sh"


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_pubsub_api_is_enabled():
    """Mutation: remove the pubsub.googleapis.com enable line -- red."""
    text = _script_text()
    assert "gcloud services enable pubsub.googleapis.com" in text, (
        "scripts/setup-admin-service.sh must enable pubsub.googleapis.com "
        "-- the build-status webhook (bd polyglot-pdf-tb3kp) needs a "
        "push subscription, and Cloud Build cannot publish to a topic "
        "without this API enabled.")


def test_cloud_builds_topic_is_created_if_absent():
    """The topic-create block must be IDEMPOTENT (describe-then-create),
    matching every other resource this script provisions -- a bare
    `create` would fail on a re-run. Mutation: remove the `describe`
    guard -- red."""
    text = _script_text()
    assert 'CLOUD_BUILDS_TOPIC="cloud-builds"' in text, (
        "the topic name must be the literal Cloud Build publishes to "
        "automatically: 'cloud-builds'.")
    assert "gcloud pubsub topics describe" in text, (
        "the topic creation must be idempotent (describe-then-create), "
        "matching every other resource this script provisions.")
    assert "gcloud pubsub topics create" in text


def test_a_dedicated_push_caller_sa_is_declared_and_it_is_neither_runtime_sa():
    """The push subscription's OWN caller identity must be a THIRD service
    account -- neither admin-backend-sa (the webhook's own CALLEE identity)
    nor polyglot-cloudbuild-sa (the BUILD identity) -- because require_
    google_oidc's whole point is pinning a caller identity DIFFERENT from
    the service it calls. Mutation: set PUBSUB_PUSH_SA_NAME to
    "admin-backend-sa" -- red."""
    text = _script_text()
    assert 'PUBSUB_PUSH_SA_NAME="admin-pubsub-push-sa"' in text, (
        "the Pub/Sub push caller must be its own dedicated service "
        "account, not admin-backend-sa or polyglot-cloudbuild-sa.")
    assert "admin-pubsub-push-sa" != "admin-backend-sa"
    assert "gcloud iam service-accounts create" in text
    assert "PUBSUB_PUSH_SA_NAME" in text


def test_push_subscription_note_names_the_topic_and_the_webhook_path():
    """The printed (not executed) subscription-create command must name
    the RIGHT topic and the webhook's OWN route path -- a wrong path here
    would leave an operator creating a subscription that pushes to a route
    that does not exist. Mutation: change the --push-endpoint path from
    /api/deploys/webhook to something else -- red."""
    text = _script_text()
    assert "gcloud pubsub subscriptions create cloud-builds-webhook" in text
    assert "--topic=" in text and "cloud-builds" in text
    assert "/api/deploys/webhook" in text, (
        "the push subscription's endpoint and audience must both name "
        "the webhook route's own path, /api/deploys/webhook.")


def test_push_subscription_note_carries_both_push_auth_flags():
    """Both --push-auth-service-account and --push-auth-token-audience
    must be present -- omitting either would let Pub/Sub push without an
    OIDC token at all (require_google_oidc would then refuse every call
    with 401, and every build would look stuck at 'queued' forever with no
    application-level error to grep for -- the exact failure mode
    admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py's sibling
    test warns about on the token-creator side). Mutation: delete either
    flag from the printed command -- red."""
    text = _script_text()
    assert "--push-auth-service-account=" in text
    assert "--push-auth-token-audience=" in text
    assert "PUBSUB_PUSH_SA_EMAIL" in text, (
        "the --push-auth-service-account flag must reference the "
        "dedicated push caller's own email variable, not a hard-coded "
        "string or the wrong service account.")

def test_the_subscription_is_declared_not_executed():
    """Creating the push subscription needs the admin service's OWN
    Cloud Run URL, unknown until after its first deploy -- same reasoning
    as the sweep job's scheduler command. Mutation: move the command onto
    a bare (non-echo) line -- red (this script has no live project to run
    gcloud against in CI).

    Checked per PHYSICAL SOURCE LINE, not a substring-sliced block (which
    can start mid-line inside an echo's own quoted text and misattribute
    line boundaries): the line that names the subscription-create command
    must itself be an echo statement.
    """
    lines = _script_text().splitlines()
    saw_command = False
    for line in lines:
        if "gcloud pubsub subscriptions create" not in line:
            continue
        saw_command = True
        stripped = line.strip()
        assert stripped.startswith("echo"), (
            "the subscription-create command must be a printed NOTE (an "
            "echo line), not a bare, directly-executed gcloud invocation "
            "-- found: {!r}".format(line))
    assert saw_command, "could not find the subscription-create command"
