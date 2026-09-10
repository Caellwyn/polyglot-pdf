"""scripts/setup-monitoring.sh's declared metrics, policies, uptime checks
and IAM grants (Epic 3 bead 8, E3.8).

This is an OPERATOR script -- no deploy pipeline runs it, and no CI step
executes gcloud -- so the only mechanical guard available is pinning the
SHIPPED SCRIPT TEXT, matching tests/test_setup_telemetry_script.py,
tests/test_setup_firestore_ttl_script.py and
tests/test_setup_admin_service_scheduler.py.

WHY THE FILTER SHAPES GET THEIR OWN TESTS. This repo emits log lines through
TWO different renderers, and a filter written against the wrong one matches
NOTHING while the script still exits 0:

  * StructuredLogger._emit (backend/utils/structured_logger.py) wraps the
    whole envelope in a `message` key before printing, so its event type is
    at jsonPayload.message.event_type. The ws_error events the two
    ws_close_* metrics count are this shape, and their close code is one
    level deeper still, at jsonPayload.message.metadata.close_code.
  * A plain structlog call renders the POSITIONAL event name at
    jsonPayload.event with no wrapper. backend/routes/link_routes.py's
    `_log.info("link_mint_refused", ...)` -- what mint_refused_count counts
    -- is this shape.

The failure mode of getting this wrong is an alert that NEVER FIRES, which
nothing else in the system would ever notice: the metric exists, the policy
is green, and the outage it was built for goes unreported. That is why the
depth of each filter path is asserted, not just the presence of the field
names.

ASCII only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-monitoring.sh"


def _script_text() -> str:
    assert SCRIPT.is_file(), (
        "scripts/setup-monitoring.sh is missing. It is the script this "
        "whole file asserts against.")
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists_and_starts_with_a_shebang():
    """git tracks these sibling scripts as mode 100644 on this repo and
    Windows stat() never reports S_IXUSR, so the shebang -- not the
    executable bit -- is what actually governs `bash scripts/foo.sh`."""
    assert _script_text().startswith("#!/bin/bash")


def test_script_is_ascii_only():
    """CLAUDE.md scar #6. A .sh is a source file."""
    raw = SCRIPT.read_bytes()
    bad = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not bad, (
        "non-ASCII byte(s) in setup-monitoring.sh at offsets "
        + repr(bad[:5]))


def test_script_requires_a_project_id_argument():
    """Mutation: drop the PROJECT_ID empty-check / exit 1 -- red.

    Without it, every gcloud call below runs against whatever project the
    operator's gcloud happens to be pointed at, which on this machine is a
    real one.
    """
    text = _script_text()
    assert 'PROJECT_ID=$1' in text
    assert re.search(r'if \[ -z "\$PROJECT_ID" \]', text), (
        "no guard on a missing PROJECT_ID")
    assert "exit 1" in text


# ---------------------------------------------------------------------------
# The three log-based metrics
# ---------------------------------------------------------------------------

EXPECTED_METRICS = (
    "ws_close_1011_count",
    "ws_close_1013_count",
    "mint_refused_count",
)


@pytest.mark.parametrize("metric", EXPECTED_METRICS)
def test_metric_is_declared(metric):
    """Each of the three metrics the bead names is actually created."""
    text = _script_text()
    assert '"{}"'.format(metric) in text, (
        "setup-monitoring.sh does not declare the log-based metric "
        + metric)


def test_no_undeclared_metrics_and_no_missing_ones():
    """The SET of metrics, pinned (CLAUDE.md scar #8).

    Parsed out of the create_or_update_metric calls rather than grepped for
    the three known names, so a FOURTH metric added without a decision --
    each one is a standing Cloud Logging cost and a thing the console has to
    render -- fails here rather than shipping unnoticed.
    """
    text = _script_text()
    declared = re.findall(
        r'create_or_update_metric \\\s*\n\s*"([a-z0-9_]+)"', text)
    assert set(declared) == set(EXPECTED_METRICS), (
        "the metrics setup-monitoring.sh declares ({}) are not the set this "
        "bead pins ({})".format(sorted(declared), sorted(EXPECTED_METRICS)))


def test_metric_creation_is_idempotent():
    """describe-then-create-or-update, not create-only.

    `gcloud logging metrics create` FAILS on a metric that already exists, so
    a create-only script cannot be how a re-run applies a CHANGED filter --
    it would leave the live metric counting the old filter forever. This is
    the same trap bd polyglot-pdf-f7f0h caught in setup-telemetry.sh's sink
    step. Mutation: delete the `gcloud logging metrics update` branch -- red.
    """
    text = _script_text()
    assert "gcloud logging metrics describe" in text, (
        "no describe step -- the script cannot tell create from update")
    assert "gcloud logging metrics update" in text, (
        "no update branch: a re-run after a filter change would fail on "
        "create and leave the live metric stale")
    assert "gcloud logging metrics create" in text


def test_ws_close_metrics_filter_the_nested_structured_logger_shape():
    """The two ws_* metrics must read the NESTED path, not a flat one.

    StructuredLogger._emit wraps its envelope in a `message` key, so a filter
    on jsonPayload.event_type (the shape the plan prose implies) matches
    nothing at all. Asserting the DEPTH is the point: the field names alone
    would pass under the broken form.
    """
    text = _script_text()
    for code in ("1011", "1013"):
        assert (
            'jsonPayload.message.metadata.close_code={}'.format(code)
            in text
        ), (
            "the ws_close_{}_count filter does not read the close code at "
            "jsonPayload.message.metadata.close_code -- StructuredLogger "
            "nests its envelope under `message`, so a shallower path counts "
            "zero forever".format(code))

    assert 'jsonPayload.message.event_type="ws_error"' in text, (
        "the ws close metrics do not filter on the ws_error event_type at "
        "the nested path")
    # And the flat form must NOT be used for these -- that is the bug.
    assert 'jsonPayload.event_type="ws_error"' not in text, (
        "a ws_error filter is written at the FLAT jsonPayload.event_type "
        "path; StructuredLogger never emits that shape, so it counts zero")


def test_mint_refused_metric_filters_the_plain_structlog_shape():
    """mint_refused_count reads jsonPayload.event, NOT the nested path.

    link_routes.py logs this through a plain structlog call with no
    event_type kwarg, so the positional name renders under "event". Copying
    the ws metrics' nested filter here would produce a metric that counted
    zero forever -- and this test is what catches that copy-paste.
    """
    text = _script_text()
    assert 'jsonPayload.event="link_mint_refused"' in text, (
        "mint_refused_count does not filter on jsonPayload.event")
    assert 'jsonPayload.message.event_type="link_mint_refused"' not in text, (
        "mint_refused_count uses the NESTED path, but link_mint_refused is "
        "a plain structlog event that renders flat at jsonPayload.event")


def test_the_metric_filter_event_names_exist_in_the_backend():
    """The names the filters count are names the app actually EMITS.

    Derived from the source, not asserted against a copy of the string in
    this file -- a filter naming an event nobody emits is indistinguishable,
    from the console, from an outage that never happens.
    """
    link_routes = (REPO_ROOT / "backend" / "routes"
                   / "link_routes.py").read_text(encoding="utf-8")
    assert '"link_mint_refused"' in link_routes, (
        "setup-monitoring.sh counts link_mint_refused, but "
        "backend/routes/link_routes.py does not emit it")

    schemas = (REPO_ROOT / "backend" / "utils"
               / "log_schemas.py").read_text(encoding="utf-8")
    assert '"ws_error"' in schemas, (
        "the ws close metrics count event_type ws_error, but it is not a "
        "declared EventType in backend/utils/log_schemas.py")


def test_the_close_codes_counted_are_codes_the_app_classifies():
    """1011 and 1013 are in the shipped WS_CLOSE_SEVERITY table.

    A metric counting a code the app never emits through log_ws_close would
    read zero forever. This ties the script to the code rather than to the
    bead prose.
    """
    logger_src = (REPO_ROOT / "backend" / "utils"
                  / "structured_logger.py").read_text(encoding="utf-8")
    for code in ("1011", "1013"):
        assert re.search(r"^\s*{}: \"".format(code), logger_src, re.MULTILINE), (
            "close code {} is counted by setup-monitoring.sh but is not in "
            "WS_CLOSE_SEVERITY".format(code))


# ---------------------------------------------------------------------------
# The two alert policies
# ---------------------------------------------------------------------------

EXPECTED_POLICIES = (
    "polyglot 5xx rate",
    "polyglot ws 1011 rate",
)


@pytest.mark.parametrize("policy", EXPECTED_POLICIES)
def test_alert_policy_is_declared_and_applied(policy):
    """Each policy is both DEFINED (a displayName in its JSON) and APPLIED.

    Two separate things: a policy body written to a temp file that no
    apply_policy call ever consumes would satisfy a naive presence check
    while creating nothing.
    """
    text = _script_text()
    assert '"displayName": "{}"'.format(policy) in text, (
        "no policy body with displayName " + policy)
    assert 'apply_policy "{}"'.format(policy) in text, (
        "the policy body for {} is never passed to apply_policy, so nothing "
        "creates it".format(policy))


def test_no_undeclared_alert_policies():
    """The SET of policies, pinned. Every alert is a page someone gets."""
    text = _script_text()
    applied = re.findall(r'apply_policy "([^"]+)"', text)
    assert set(applied) == set(EXPECTED_POLICIES), (
        "the policies setup-monitoring.sh applies ({}) are not the set this "
        "bead pins ({})".format(sorted(applied), sorted(EXPECTED_POLICIES)))


def test_alert_policy_bodies_are_valid_json():
    """Each heredoc body parses as JSON with the channel placeholder filled.

    gcloud rejects a malformed --policy-from-file at RUN time, on the
    operator's machine, after the metrics have already been created. Parsing
    it here moves that failure into CI.
    """
    text = _script_text()
    bodies = re.findall(
        r"<<POLICY_\w+_EOF\n(.*?)\nPOLICY_\w+_EOF", text, re.DOTALL)
    assert len(bodies) == len(EXPECTED_POLICIES), (
        "expected {} policy heredocs, found {}".format(
            len(EXPECTED_POLICIES), len(bodies)))

    for body in bodies:
        # The only shell expansion inside these bodies is the notification
        # channels array; substitute the no-channel form the script itself
        # produces when no channel id is passed.
        filled = body.replace("$NOTIFICATION_CHANNELS_JSON", "[]")
        parsed = json.loads(filled)  # raises on malformed JSON
        assert parsed["conditions"], "policy has no conditions"
        assert parsed["enabled"] is True, (
            "a policy is declared DISABLED -- it would never fire")
        cond = parsed["conditions"][0]["conditionThreshold"]
        assert cond["comparison"] == "COMPARISON_GT"
        assert cond["thresholdValue"] > 0, (
            "a threshold of 0 fires on the first matching event, turning the "
            "policy into a per-event pager")


def test_policies_alert_on_a_RATE_not_a_raw_count():
    """ALIGN_RATE, not ALIGN_SUM/ALIGN_COUNT.

    A raw count fires on a traffic spike that is proportionally healthy and
    stays silent on a low-traffic outage where every request fails. Mutation:
    change perSeriesAligner to ALIGN_SUM -- red.
    """
    text = _script_text()
    bodies = re.findall(
        r"<<POLICY_\w+_EOF\n(.*?)\nPOLICY_\w+_EOF", text, re.DOTALL)
    for body in bodies:
        parsed = json.loads(body.replace("$NOTIFICATION_CHANNELS_JSON", "[]"))
        agg = parsed["conditions"][0]["conditionThreshold"]["aggregations"][0]
        assert agg["perSeriesAligner"] == "ALIGN_RATE", (
            "policy {!r} aligns on {} rather than a RATE".format(
                parsed["displayName"], agg["perSeriesAligner"]))


def test_the_1011_policy_reads_this_scripts_own_metric():
    """The 1011 policy's filter names the log-based metric created above.

    A policy pointed at a metric type that does not exist evaluates forever
    without ever firing -- the silent-failure shape this whole file guards.
    """
    text = _script_text()
    assert (
        'metric.type=\\"logging.googleapis.com/user/ws_close_1011_count\\"'
        in text
    ), ("the 1011 policy does not read "
        "logging.googleapis.com/user/ws_close_1011_count -- the metric this "
        "same script creates")


def test_the_5xx_policy_reads_cloud_runs_builtin_request_count():
    """The 5xx policy uses Cloud Run's own metric, not a log-based one.

    Deliberate: Cloud Run already counts responses by class, so building a
    log-based 5xx metric would be a second, lagging, more expensive copy of
    a number the platform publishes.
    """
    text = _script_text()
    assert 'run.googleapis.com/request_count' in text
    assert 'response_code_class=\\"5xx\\"' in text


def test_policy_application_is_idempotent():
    """apply_policy lists-then-creates-or-updates.

    Alert policies have no operator-chosen id, so a create-only script makes
    a DUPLICATE policy on every re-run -- and the operator then gets two
    pages per incident, with the old thresholds still live on the stale one.
    """
    text = _script_text()
    assert "gcloud alpha monitoring policies list" in text, (
        "apply_policy does not look for an existing policy, so a re-run "
        "creates a duplicate")
    assert "gcloud alpha monitoring policies update" in text
    assert "gcloud alpha monitoring policies create" in text


# ---------------------------------------------------------------------------
# Uptime checks -- one per channel
# ---------------------------------------------------------------------------

EXPECTED_UPTIME_CHECKS = {
    "polyglot demo health": "$BACKEND_SERVICE",
    "polyglot staging health": "$STAGING_SERVICE",
    "polyglot admin health": "$ADMIN_SERVICE",
}


@pytest.mark.parametrize(
    "display_name,service_var", sorted(EXPECTED_UPTIME_CHECKS.items()))
def test_uptime_check_per_channel(display_name, service_var):
    """One uptime check per CHANNEL, each against its own Cloud Run service.

    Staging and demo run DIFFERENT CODE on the same project
    (docs/doctrine/promotion-tiers.md), so a single shared check would either
    miss a broken demo or page on a staging channel that is EXPECTED to be
    broken.
    """
    text = _script_text()
    expected = 'create_or_update_uptime_check "{}" "{}"'.format(
        display_name, service_var)
    assert expected in text, (
        "no per-channel uptime check for " + display_name)


def test_no_undeclared_uptime_checks():
    """The SET of uptime checks, pinned."""
    text = _script_text()
    declared = re.findall(
        r'create_or_update_uptime_check "([^"]+)" "([^"]+)"', text)
    assert dict(declared) == EXPECTED_UPTIME_CHECKS, (
        "the uptime checks setup-monitoring.sh declares ({}) are not the set "
        "this bead pins ({})".format(
            sorted(declared), sorted(EXPECTED_UPTIME_CHECKS.items())))


def test_uptime_checks_probe_health_not_the_root_path():
    """/health, which now carries BOTH Firestore probes.

    A check on / would go green on a process that is up but cannot write the
    audit trail or read firm data -- the exact silent failures the two probes
    exist to surface (bd z2is, bd polyglot-pdf-vq5wd).
    """
    text = _script_text()
    assert '--path="/health"' in text, (
        "the uptime checks do not probe /health")


def test_uptime_check_service_names_match_the_deploy_scripts():
    """The three service names are the ones the deploy scripts actually use.

    Derived from those scripts, not from a copy here: a rename on either side
    otherwise leaves a check monitoring a service that no longer exists,
    which reads as a permanent outage or a permanent silence depending on
    which way it broke.
    """
    text = _script_text()
    deploy_all = (REPO_ROOT / "deploy-all.sh").read_text(encoding="utf-8")
    deploy_staging = (REPO_ROOT / "deploy-staging.sh").read_text(
        encoding="utf-8")

    assert 'BACKEND_SERVICE_NAME:-polyglot-backend}' in deploy_all, (
        "deploy-all.sh's default backend service name changed")
    assert 'ADMIN_SERVICE_NAME:-polyglot-admin}' in deploy_all, (
        "deploy-all.sh's default admin service name changed")
    assert 'STAGING_SERVICE_NAME="polyglot-backend-staging"' in deploy_staging, (
        "deploy-staging.sh's service name changed")

    for name in ("polyglot-backend", "polyglot-backend-staging",
                 "polyglot-admin"):
        assert '"{}"'.format(name) in text, (
            "setup-monitoring.sh does not name the Cloud Run service "
            + name)


def test_uptime_creation_is_idempotent():
    """list-configs-then-create-or-update.

    An uptime check has no operator-chosen id either, so a create-only script
    multiplies the checks on every re-run -- and each one bills separately.
    """
    text = _script_text()
    assert "gcloud monitoring uptime list-configs" in text
    assert "gcloud monitoring uptime update" in text
    assert "gcloud monitoring uptime create" in text


def test_uptime_check_skips_a_service_that_is_not_deployed():
    """A missing service is SKIPPED with a note, not a hard failure.

    `set -e` is on, so an unguarded describe of an undeployed service would
    abort the whole script -- leaving the metrics and policies half-applied
    on a fresh project where the admin service does not exist yet.
    """
    text = _script_text()
    assert re.search(r'if \[ -z "\$host" \]', text), (
        "no guard for an undeployed Cloud Run service")
    assert "return 0" in text, (
        "the undeployed-service branch does not return cleanly")


# ---------------------------------------------------------------------------
# The two deferred IAM roles
# ---------------------------------------------------------------------------

EXPECTED_DEFERRED_GRANTS = (
    "roles/errorreporting.viewer",
    "roles/monitoring.viewer",
)


@pytest.mark.parametrize("role", EXPECTED_DEFERRED_GRANTS)
def test_admin_sa_role_is_granted_project_level(role):
    """Both roles are granted to admin-backend-sa at the PROJECT level.

    Scope matters as much as the role name: Error Reporting groups and
    Monitoring metrics are project-scoped resources, so unlike the BigQuery
    dataViewer grant in setup-telemetry.sh there is no narrower scope to use.
    """
    text = _script_text()
    assert 'ADMIN_SA_EMAIL="admin-backend-sa@$PROJECT_ID' in text, (
        "the script does not resolve admin-backend-sa's email")
    assert '--role="{}"'.format(role) in text, (
        "setup-monitoring.sh does not grant " + role)
    assert re.search(
        r'gcloud projects add-iam-policy-binding "\$PROJECT_ID"[^\n]*\n'
        r'\s*--member="serviceAccount:\$ADMIN_SA_EMAIL"[^\n]*\n'
        r'\s*--role="{}"'.format(re.escape(role)),
        text,
    ), ("{} is not granted with `gcloud projects add-iam-policy-binding` to "
        "$ADMIN_SA_EMAIL".format(role))


def test_the_public_backend_sa_gets_neither_role():
    """polyglot-backend-sa's envelope stays narrow (CLAUDE.md scar #7).

    It writes logs; it never reads a metric or an error group back. Granting
    it either role would widen the blast radius of a compromise for a
    capability nothing calls.
    """
    text = _script_text()
    assert "polyglot-backend-sa@" not in text, (
        "setup-monitoring.sh references polyglot-backend-sa -- the public "
        "backend's identity must not gain monitoring read roles")


def test_no_undeclared_iam_grants():
    """The SET of roles this script grants, pinned.

    An IAM grant appearing in a provisioning script is exactly the change a
    reviewer must be forced to look at; without this the third role slips in
    with the commit that needed it.
    """
    text = _script_text()
    granted = set(re.findall(r'--role="(roles/[^"]+)"', text))
    assert granted == set(EXPECTED_DEFERRED_GRANTS), (
        "setup-monitoring.sh grants {} but this bead pins {}".format(
            sorted(granted), sorted(EXPECTED_DEFERRED_GRANTS)))
