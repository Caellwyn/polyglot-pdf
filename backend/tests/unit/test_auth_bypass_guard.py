"""Auth-bypass fail-closed guard (bd polyglot-pdf-knmp).

`VFF_DISABLE_AUTH=true` makes verify_token return a stub user for EVERY
caller. Since bd polyglot-pdf-z2is that single bypass gates /ws/fill AND every
require_auth route -- including /api/fill-pdf, which renders the client's
entered PII into a PDF. The service deploys --allow-unauthenticated, so before
this guard a stray `--set-env-vars VFF_DISABLE_AUTH=true` on Cloud Run made the
whole backend world-open with no startup failure and only a per-request warning
log.

Two layers, both pinned here (K_SERVICE is set by Cloud Run and nothing else,
the same deployment signal test_vertexai_guard.py keys on):

  1. STARTUP -- Settings refuses to construct, so a deployed service with the
     flag set cannot boot at all.
  2. RUNTIME -- verify_token ignores the bypass when K_SERVICE is set and falls
     through to real verification, so the request fails CLOSED even where
     Settings was never constructed.

Layer 2 is deliberately NOT redundant: a test that only pinned layer 1 would
stay green if someone deleted the runtime check, and vice versa (the
redundant-guards-need-per-layer-tests lesson). Each layer gets its own case.

Fresh Settings() per test, never get_settings() -- it is lru_cached and
ordering-fragile (the get-settings-singleton memory).

ASCII only.
"""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.config import Settings
from backend.services import auth as auth_service


# --------------------------------------------------------------------------- #
# Layer 1 -- startup
# --------------------------------------------------------------------------- #

def test_auth_bypass_on_cloud_run_fails_startup(monkeypatch):
    """The core policy: a deployed build cannot run with auth disabled."""
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    with pytest.raises(ValidationError, match="not permitted on a deployed service"):
        Settings()


def test_the_startup_guard_names_the_flag_not_just_the_policy(monkeypatch):
    """The message must say WHICH flag to unset.

    A deploy that dies with only "not permitted on a deployed service" is
    indistinguishable from the sibling VERTEXAI failure, and an operator
    reading the crash has to guess which env var to pull.
    """
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "VFF_DISABLE_AUTH" in str(exc.value)


@pytest.mark.parametrize("flag", ["TRUE", "True", "tRuE"])
def test_the_guard_is_case_insensitive_like_the_reader(monkeypatch, flag):
    """The guard must parse the flag EXACTLY as auth.py does (.lower()).

    A case-sensitive guard would let VFF_DISABLE_AUTH=TRUE boot while
    verify_token's own .lower() comparison still honored it -- the guard
    passing and the bypass live at the same time.
    """
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("VFF_DISABLE_AUTH", flag)
    with pytest.raises(ValidationError, match="not permitted on a deployed service"):
        Settings()


def test_no_override_flag_can_re_enable_the_bypass_on_cloud_run(monkeypatch):
    """There must be NO escape hatch, for the same reason the AI Studio guard
    has none: no legitimate deployed use of a blanket auth bypass exists."""
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    for hatch in ("ALLOW_AUTH_BYPASS", "ALLOW_DISABLE_AUTH", "VFF_ALLOW_BYPASS"):
        monkeypatch.setenv(hatch, "true")
    with pytest.raises(ValidationError, match="not permitted on a deployed service"):
        Settings()


def test_a_deployed_service_without_the_flag_starts_normally(monkeypatch):
    """The guard must fire ONLY on the bypass -- an ordinary deploy is fine."""
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.delenv("VFF_DISABLE_AUTH", raising=False)
    Settings()                                   # must not raise
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    Settings()                                   # must not raise


def test_local_dev_with_the_bypass_still_starts(monkeypatch):
    """Criterion 2: no K_SERVICE -> local dev / the voice harness are
    unaffected. dev-local.ps1 and dev-local.sh both default this flag to true,
    so a guard that fired locally would break every local run."""
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    Settings()                                   # must not raise


# --------------------------------------------------------------------------- #
# Layer 2 -- runtime (verify_token)
# --------------------------------------------------------------------------- #

def test_verify_token_ignores_the_bypass_on_a_deployed_service(monkeypatch):
    """The bypass must be INERT when K_SERVICE is set, even though startup
    should already have refused -- this layer holds where Settings was never
    constructed. The call falls through to real verification, which rejects a
    junk token, so the request fails CLOSED rather than returning a stub user.
    """
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    # Real verification is reached and refuses; no stub user comes back.
    with pytest.raises(HTTPException) as exc:
        auth_service.verify_token("not-a-real-token")
    assert exc.value.status_code == 401


def test_verify_token_honors_the_bypass_locally(monkeypatch):
    """Criterion 2, runtime half: local dev keeps its tokenless path."""
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    assert auth_service.verify_token("ignored")["uid"] == "dev_user"


@pytest.mark.parametrize("flag", ["TRUE", "True"])
def test_the_runtime_guard_matches_the_readers_case_handling(monkeypatch, flag):
    """Same case-insensitivity contract as the startup guard: whatever spelling
    turns the bypass ON must also be the spelling the deployed check catches."""
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("VFF_DISABLE_AUTH", flag)
    with pytest.raises(HTTPException):
        auth_service.verify_token("not-a-real-token")
