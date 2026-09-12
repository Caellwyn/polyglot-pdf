"""deploy-admin.sh must resolve BACKEND_URLS_JSON and fold it into
BACKEND_EXTRA_ENV on every run (bd polyglot-pdf-mpebj, E3.11a).

WHY THIS EXISTS. GET /admin/health (admin_backend/routes/ops_routes.py)
fans out to each channel's public backend /health + /version, and needs to
know that backend's Cloud Run URL -- unknowable to the admin service
itself (it has no channel of its own). deploy-admin.sh resolves BOTH
public backends' URLs via `gcloud run services describe`, the same
mechanism it already uses for ADMIN_SERVICE_URL (see
test_deploy_admin_sweep_env_vars.py, the sibling this file mirrors).

WHY THE WIRE FORMAT IS "channel=url;channel=url", NOT LITERAL JSON, DESPITE
THE ENV VAR'S NAME. BACKEND_URLS_JSON rides inside BACKEND_EXTRA_ENV, which
deploy-all.sh joins into ONE comma-separated --set-env-vars string -- a
literal JSON object's "," between key/value pairs would be silently split
apart there as a malformed second env-var entry, the same reason
CORS_EXTRA_ORIGINS is semicolon-separated rather than comma-separated (see
test_deploy_admin_cors_origins.py). This file pins the SEMICOLON shape, not
a JSON shape.

WHY STATIC-TEXT ASSERTION, NOT AN EXECUTED SHELL DRIVE (mirrors
test_deploy_admin_sweep_env_vars.py's own reasoning for the same file): the
logic under test is a short, straight-line set of gcloud lookups and string
concatenations near the top of deploy-admin.sh, not a conditional flow
whose branches need a real shell to exercise.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ADMIN = REPO_ROOT / "deploy-admin.sh"


def _live_text(path: Path) -> str:
    """Strip full-line `#` comments so a commented-out assignment can't be
    parsed as the real one (mirrors test_deploy_admin_sweep_env_vars.py's
    own helper of the same name, for the same file)."""
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    ]
    return "\n".join(lines)


def test_both_backend_urls_are_resolved_via_gcloud_before_the_deploy_all_call():
    """deploy-admin.sh must look up BOTH polyglot-backend and
    polyglot-backend-staging's Cloud Run URLs (via `gcloud run services
    describe`) BEFORE its ./deploy-all.sh call. Mutation: delete either
    lookup -- this goes red."""
    text = _live_text(DEPLOY_ADMIN)
    deploy_all_call = text.index("./deploy-all.sh --backend")
    before_deploy = text[:deploy_all_call]

    assert re.search(
        r'DEMO_BACKEND_URL=\$\(gcloud run services describe '
        r'"polyglot-backend"', before_deploy), (
        "deploy-admin.sh does not resolve the demo public backend's URL "
        "via `gcloud run services describe \"polyglot-backend\"` before "
        "the ./deploy-all.sh call")
    assert re.search(
        r'STAGING_BACKEND_URL=\$\(gcloud run services describe '
        r'"polyglot-backend-staging"', before_deploy), (
        "deploy-admin.sh does not resolve the staging public backend's "
        "URL via `gcloud run services describe "
        "\"polyglot-backend-staging\"` before the ./deploy-all.sh call")

    # Both lookups must tolerate a not-yet-deployed service (2>/dev/null ||
    # true) rather than aborting the whole script under `set -e`.
    for var in ("DEMO_BACKEND_URL", "STAGING_BACKEND_URL"):
        assert re.search(
            r'{}=\$\(gcloud run services describe[^\n]*\n'
            r'(?:[^\n]*\n)*?[^\n]*2>/dev/null \|\| true\)'.format(var),
            before_deploy), (
            "{}'s gcloud lookup must swallow a not-yet-existing service "
            "(2>/dev/null || true) rather than aborting under `set -e`"
            .format(var))


def test_backend_urls_json_reaches_backend_extra_env():
    """THE SET GUARD (mirrors test_both_sweep_env_vars_reach_backend_extra_
    env). BACKEND_URLS_JSON must actually reach the BACKEND_EXTRA_ENV
    passed to ./deploy-all.sh -- computing it and never using it is exactly
    as broken as not computing it. Mutation: compute BACKEND_URLS_PARTS but
    drop it from the env assignment chain -- this goes red."""
    text = _live_text(DEPLOY_ADMIN)
    deploy_all_call = text.index("./deploy-all.sh --backend")
    before_deploy = text[:deploy_all_call]

    extra_env_match = re.search(
        r'BACKEND_EXTRA_ENV="([^"]*)"', before_deploy)
    assert extra_env_match, (
        "no BACKEND_EXTRA_ENV assignment found before the ./deploy-all.sh "
        "call in deploy-admin.sh")
    extra_env_value = extra_env_match.group(1)

    # Resolve every bare $VARNAME reference inside BACKEND_EXTRA_ENV's value
    # against every assignment to that name anywhere earlier in the script
    # (mirrors test_deploy_admin_sweep_env_vars.py's own resolution walk --
    # SWEEP_ENV is itself built across more than one statement, and
    # BACKEND_URLS_JSON is folded into that same SWEEP_ENV chain).
    referenced_vars = re.findall(r'\$([A-Za-z_][A-Za-z0-9_]*)', extra_env_value)
    resolved = extra_env_value
    seen = set()
    frontier = list(referenced_vars)
    while frontier:
        var_name = frontier.pop()
        if var_name in seen:
            continue
        seen.add(var_name)
        for var_match in re.finditer(
                r'{}="([^"]*)"'.format(re.escape(var_name)), before_deploy):
            resolved += " " + var_match.group(1)
            frontier.extend(
                re.findall(r'\$([A-Za-z_][A-Za-z0-9_]*)', var_match.group(1)))

    assert "BACKEND_URLS_JSON" in resolved, (
        "deploy-admin.sh computes BACKEND_URLS_PARTS but never folds a "
        "BACKEND_URLS_JSON=... assignment into BACKEND_EXTRA_ENV (directly, "
        "or via a referenced intermediate variable) -- GET /admin/health "
        "would read every channel as configured: false on every deploy")


def test_backend_urls_json_value_is_semicolon_joined_not_comma_joined():
    """THE WIRE-FORMAT PIN. BACKEND_URLS_PARTS must be assembled with a
    semicolon between the demo and staging segments, never a comma --
    a comma would be silently split apart by deploy-all.sh's own
    comma-joined --set-env-vars assembly (see module docstring). Mutation:
    change the join character to "," -- this goes red."""
    text = _live_text(DEPLOY_ADMIN)
    deploy_all_call = text.index("./deploy-all.sh --backend")
    before_deploy = text[:deploy_all_call]

    assert 'BACKEND_URLS_PARTS="$BACKEND_URLS_PARTS;staging=' in before_deploy, (
        "deploy-admin.sh does not join the demo and staging segments of "
        "BACKEND_URLS_PARTS with a semicolon -- a comma here would be "
        "silently split apart by deploy-all.sh's own comma-joined "
        "--set-env-vars assembly, corrupting the env block")
    # And the negative: no comma-joined form anywhere in the construction.
    assert 'BACKEND_URLS_PARTS,staging=' not in before_deploy
    assert '$BACKEND_URLS_PARTS,staging=' not in before_deploy


def test_ops_routes_parses_the_same_semicolon_shape_deploy_admin_produces():
    """Cross-checks admin_backend/routes/ops_routes.py's own parser against
    what deploy-admin.sh actually emits -- the two sides of this contract
    must agree on the wire format without a test importing shell into
    Python or vice versa. Mutation: change ops_routes.py's separator to ","
    without updating this test (or deploy-admin.sh) -- this test would
    still pass ITS OWN assertions (it does not exercise ops_routes.py
    directly), which is exactly why admin_backend/tests/unit/
    test_ops_routes.py's own semicolon-parsing test is the other half of
    this pin; this test only confirms deploy-admin.sh's own shape did not
    drift to match a hypothetical format ops_routes.py never asked for."""
    ops_routes_path = REPO_ROOT / "admin_backend" / "routes" / "ops_routes.py"
    ops_routes_text = ops_routes_path.read_text(encoding="utf-8")
    assert 'raw.split(";")' in ops_routes_text, (
        "admin_backend/routes/ops_routes.py's _backend_urls no longer "
        "splits BACKEND_URLS_JSON on \";\" -- re-verify it still agrees "
        "with deploy-admin.sh's own semicolon-joined BACKEND_URLS_PARTS "
        "construction")
