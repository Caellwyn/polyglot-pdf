"""Vertex-only production guard (bd polyglot-pdf-z2is, hardened by 5e6a).

MAINTAINER DIRECTIVE (2026-08-04): AI Studio is NEVER a production path. Only
Vertex's privacy agreement prevents Google from using client data for model
training, and the product's privacy promise rests on that. AI Studio is
permitted ONLY for local development (e.g. testing 3.1 before it reaches Vertex
GA); 3.1 deploys only once it is GA for Vertex customers.

So on a DEPLOYED service (K_SERVICE set by Cloud Run) `VERTEXAI=false` must
fail startup with NO override flag. The earlier `ALLOW_AI_STUDIO`
acknowledgment escape hatch was REMOVED -- these tests pin that it cannot come
back by accident.

Fresh Settings() per test (never get_settings() -- it is lru_cached and
ordering-fragile; see the get-settings-singleton memory).
"""
import pytest
from pydantic import ValidationError

from backend.config import (
    MODEL_NATIVE_STANDARD,
    MODEL_NATIVE_STANDARD_VERTEX,
    Settings,
)


def test_ai_studio_on_cloud_run_fails_startup(monkeypatch):
    """The core policy: a deployed build cannot reach AI Studio."""
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    with pytest.raises(ValidationError, match="not permitted on a deployed service"):
        Settings(VERTEXAI=False)


def test_no_override_flag_can_re_enable_ai_studio_on_cloud_run(monkeypatch):
    """There must be NO escape hatch.

    The pre-5e6a design allowed ALLOW_AI_STUDIO=true to unlock the deployed AI
    Studio path. Setting that env var (or any similarly-named one) must now be
    inert: the guard fires regardless. This is the regression that would
    silently move real client audio onto consumer terms.
    """
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    monkeypatch.setenv("ALLOW_AI_STUDIO", "true")
    with pytest.raises(ValidationError, match="not permitted on a deployed service"):
        Settings(VERTEXAI=False)


def test_allow_ai_studio_field_no_longer_exists():
    """The acknowledgment field itself is gone.

    Pinned so a future edit cannot reintroduce the flag as a settings field and
    quietly restore the escape hatch (pydantic would otherwise accept it).
    """
    assert not hasattr(Settings(), "ALLOW_AI_STUDIO")


def test_ai_studio_locally_is_still_allowed(monkeypatch):
    """No K_SERVICE (local dev / harness / probes): AI Studio stays available.

    This is the ONE sanctioned use -- testing a model (e.g. 3.1) that is not yet
    on Vertex, before any deploy.
    """
    monkeypatch.delenv("K_SERVICE", raising=False)
    settings = Settings(VERTEXAI=False, MODEL_NATIVE="")
    assert settings.MODEL_NATIVE == MODEL_NATIVE_STANDARD


def test_vertex_on_cloud_run_is_unaffected(monkeypatch):
    """The production path itself is untouched by the guard."""
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    settings = Settings(VERTEXAI=True, MODEL_NATIVE="")
    assert settings.MODEL_NATIVE == MODEL_NATIVE_STANDARD_VERTEX
