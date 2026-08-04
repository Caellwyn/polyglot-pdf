"""Fail-closed AI Studio guard on deployed builds (bd polyglot-pdf-z2is).

Vertex is the privacy-preserving path the product promise is built on; AI
Studio's consumer terms permit human review / training use of request data.
On Cloud Run (K_SERVICE set), VERTEXAI=false must be a deliberate TWO-flag
decision (ALLOW_AI_STUDIO=true) so a stray env flip fails startup loudly
instead of silently moving client audio to consumer terms. Local dev, the
voice harness, and probes have no K_SERVICE and are unaffected.

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


def test_ai_studio_on_cloud_run_without_ack_fails_startup(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    with pytest.raises(ValidationError, match="ALLOW_AI_STUDIO"):
        Settings(VERTEXAI=False, ALLOW_AI_STUDIO=False)


def test_ai_studio_on_cloud_run_with_ack_is_allowed(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    settings = Settings(VERTEXAI=False, ALLOW_AI_STUDIO=True, MODEL_NATIVE="")
    # Backend-aware resolver still picks the AI Studio id on this path.
    assert settings.MODEL_NATIVE == MODEL_NATIVE_STANDARD


def test_ai_studio_locally_needs_no_ack(monkeypatch):
    """No K_SERVICE (local dev / harness / probes): VERTEXAI=false stays free."""
    monkeypatch.delenv("K_SERVICE", raising=False)
    settings = Settings(VERTEXAI=False, ALLOW_AI_STUDIO=False, MODEL_NATIVE="")
    assert settings.MODEL_NATIVE == MODEL_NATIVE_STANDARD


def test_vertex_on_cloud_run_is_unaffected(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "polyglot-backend")
    settings = Settings(VERTEXAI=True, ALLOW_AI_STUDIO=False, MODEL_NATIVE="")
    assert settings.MODEL_NATIVE == MODEL_NATIVE_STANDARD_VERTEX
