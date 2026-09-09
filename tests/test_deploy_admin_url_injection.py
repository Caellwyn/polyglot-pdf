"""VITE_ADMIN_API_BASE_URL injection into the main-app frontend build (bd
polyglot-pdf-z4ljj, Epic 2 Track C bead C0).

WHY THIS EXISTS. The main app's firm-console pages (frontend/src/console/*)
call the admin service (polyglot-admin) over plain HTTP. Unlike the voice
WebSocket, there IS a Hosting rewrite available in principle -- but the admin
service is a SEPARATE Cloud Run service from the voice backend
($ADMIN_SERVICE_NAME vs $BACKEND_SERVICE_NAME), and firebase.json's /api/**
rewrite points only at the voice backend, so no rewrite binds the console
pages to it either. VITE_ADMIN_API_BASE_URL, resolved at deploy time from the
LIVE polyglot-admin Cloud Run URL, is therefore the only thing tying a
frontend build's firm-console pages to the admin service -- exactly the same
role VITE_WS_URL plays for the voice path (pinned by
backend/tests/unit/test_deploy_channel_isolation.py's
test_explicit_channel_fails_hard_when_backend_url_unresolvable, which this
file mirrors).

NOT tested here: that a deploy actually works. That needs a real deploy.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. ADMIN_SERVICE_NAME must be defaulted, never bare-assigned (same clobber
#    hazard BACKEND_SERVICE_NAME/FRONTEND_HOSTING_TARGET have -- CLAUDE.md
#    scar tissue #8's sibling case).
# ---------------------------------------------------------------------------


def test_admin_service_name_is_defaulted_not_bare_assigned():
    """A bare assignment would silently discard a caller's override."""
    body = _read("deploy-all.sh")
    assigns = re.findall(r"^ADMIN_SERVICE_NAME=(.*)$", body, flags=re.MULTILINE)
    assert assigns, "ADMIN_SERVICE_NAME is not assigned in deploy-all.sh at all"
    for rhs in assigns:
        assert rhs.startswith('"${ADMIN_SERVICE_NAME:-'), (
            f"deploy-all.sh assigns ADMIN_SERVICE_NAME={rhs.strip()} -- a bare "
            f"assignment would clobber a caller's export. Use "
            f'ADMIN_SERVICE_NAME="${{ADMIN_SERVICE_NAME:-<default>}}" instead.'
        )


def test_admin_service_name_default_matches_the_admin_deploy_scripts():
    """Must default to the SAME name deploy-admin.sh / deploy-admin-console.sh
    use, or a bare `./deploy-all.sh --frontend` resolves the wrong service."""
    body = _read("deploy-all.sh")
    assert 'ADMIN_SERVICE_NAME="${ADMIN_SERVICE_NAME:-polyglot-admin}"' in body


# ---------------------------------------------------------------------------
# 2. The frontend stage resolves VITE_ADMIN_API_BASE_URL from the live admin
#    service, injecting it into the build.
# ---------------------------------------------------------------------------


def test_frontend_stage_resolves_and_exports_the_admin_url():
    body = _read("deploy-all.sh")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    assert "services describe" in fe and "ADMIN_SERVICE_NAME" in fe, (
        "the frontend stage must resolve the admin service's live Cloud Run "
        "URL via `gcloud run services describe $ADMIN_SERVICE_NAME`"
    )
    assert "export VITE_ADMIN_API_BASE_URL=" in fe, (
        "the resolved admin URL must be exported as VITE_ADMIN_API_BASE_URL "
        "so it overrides the .env.<mode> fallback (standard Vite precedence)"
    )


def test_admin_url_resolution_consults_the_reachability_gate():
    """Resolving a URL proves EXISTENCE, not reachability (bd polyglot-pdf-
    pidtg/816te). Baking the admin URL into the build without checking it
    could ship a console page pinned to a service that 403s every request."""
    body = _read("deploy-all.sh")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    admin_block = fe.split("ADMIN_URL=$(gcloud")[1]
    assert "verify_service_publicly_reachable" in admin_block, (
        "the admin URL resolution must call the reachability gate"
    )


def test_admin_url_gate_call_is_warn_mode():
    """The admin service is PRE-EXISTING from this script's point of view
    (deploy-admin.sh's job, not this one's) -- same reasoning as the
    VITE_WS_URL frontend-stage call and deploy-admin-console.sh's own
    VITE_ADMIN_API_BASE_URL resolution. A fatal call here would block every
    frontend deploy over someone else's IAM state."""
    body = _read("deploy-all.sh")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    admin_block = fe.split("ADMIN_URL=$(gcloud")[1]
    call_line = next(
        ln for ln in admin_block.replace("\\\n", " ").splitlines()
        if "verify_service_publicly_reachable" in ln
        and "()" not in ln
        and not ln.strip().startswith("#")
    )
    assert re.search(r"\bwarn\b", call_line), (
        f"the admin URL reachability check must pass the literal `warn` "
        f"severity argument. Found: {call_line!r}"
    )


# ---------------------------------------------------------------------------
# 3. An EXPLICITLY-selected channel must ABORT when the admin URL cannot be
#    resolved, mirroring VITE_WS_URL's identical rule and reusing the SAME
#    "was a channel explicitly selected" signal (BACKEND_SERVICE_NAME_EXPLICIT
#    -- there is only one such signal in deploy-all.sh; a second, admin-only
#    flag would be redundant and could drift out of sync with it).
# ---------------------------------------------------------------------------


def test_explicit_channel_fails_hard_when_admin_url_unresolvable():
    """A staging deploy whose admin-service URL cannot be resolved must not
    silently fall back to a possibly-stale committed literal.

    Unlike VITE_WS_URL's fallback (which names a DIFFERENT channel's live
    backend, making a wrong-channel connection the failure mode), the admin
    service has NO channel of its own -- both staging and demo share the one
    polyglot-admin service. So the risk here is not "wrong channel"; it is
    "unresolved-at-deploy-time and possibly stale, with no way for the
    operator to tell". Aborting on an explicit channel is the same
    fail-loud choice VITE_WS_URL makes for the analogous case.
    """
    body = _read("deploy-all.sh")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    admin_block = fe.split("ADMIN_URL=$(gcloud")[1]
    assert 'elif [ -n "$BACKEND_SERVICE_NAME_EXPLICIT" ]; then' in admin_block, (
        "the admin URL resolution must branch on an EXPLICIT channel "
        "(BACKEND_SERVICE_NAME_EXPLICIT, the same signal VITE_WS_URL uses) "
        "when the admin service's URL cannot be resolved"
    )
    explicit_branch = admin_block.split(
        'elif [ -n "$BACKEND_SERVICE_NAME_EXPLICIT" ]; then'
    )[1]
    explicit_branch = explicit_branch.split("else")[0]
    assert "exit 1" in explicit_branch, (
        "an explicitly-selected channel whose admin-service URL cannot be "
        "resolved must ABORT the build, mirroring VITE_WS_URL's identical rule"
    )


def test_bare_run_warns_rather_than_aborting_on_admin_url():
    """No explicit channel (a bare `./deploy-all.sh --frontend` run) must keep
    the historical warn-and-continue behavior, exactly like VITE_WS_URL."""
    body = _read("deploy-all.sh")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    admin_block = fe.split("ADMIN_URL=$(gcloud")[1]
    explicit_branch = admin_block.split(
        'elif [ -n "$BACKEND_SERVICE_NAME_EXPLICIT" ]; then'
    )[1]
    else_branch = explicit_branch.split("else", 1)[1]
    # Scope to just the else branch's own body (up to the next `fi`).
    else_branch = else_branch.split("\n    fi", 1)[0]
    assert "log_warn" in else_branch, (
        "a non-explicit channel must WARN (not abort) when the admin URL "
        "cannot be resolved -- otherwise a bare deploy-all.sh run, which "
        "historically never aborted the frontend stage over an unresolved "
        "backend, starts failing hard for the admin service too"
    )
    assert "exit 1" not in else_branch


def test_explicit_channel_signal_is_reused_not_duplicated():
    """A SECOND explicit-channel flag for the admin resolution would be a
    duplicate source of truth that could drift from BACKEND_SERVICE_NAME's
    (CLAUDE.md scar #8: enumerate the set, then pin the set). There is
    exactly one such capture in deploy-all.sh."""
    body = _read("deploy-all.sh")
    captures = re.findall(r"^\w+_EXPLICIT=", body, flags=re.MULTILINE)
    assert captures == ['BACKEND_SERVICE_NAME_EXPLICIT='], (
        f"expected exactly one explicit-channel capture variable, found "
        f"{captures}. If a second one was added for the admin URL, either "
        f"remove it in favor of the shared signal or update this test if a "
        f"deliberate split was decided."
    )
