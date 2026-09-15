"""Pins scripts/promotion_gate.py's refusal-message remedy target
(bd polyglot-pdf-u05km).

admin-service has no separate "-staging" _TARGET (cloudbuild.yaml's
admin-service-record-deployment: one service backs both channels, and its own
tagged-candidate build records the staging row). Suggesting
_TARGET=admin-service-staging in the printed remedy hands the operator a
target cloudbuild.yaml's case match does not recognize -- it falls through to
the `*) skip` arm and does nothing, a confusing second failure on top of the
real gate refusal.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import promotion_gate  # noqa: E402


def _refusal_output(monkeypatch, target_family: str) -> str:
    monkeypatch.setattr(
        promotion_gate, "_staging_deployments_for", lambda *a, **k: []
    )
    printed: list[str] = []
    monkeypatch.setattr(
        "builtins.print",
        lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)),
    )
    code = promotion_gate.require_staging_verified(target_family, "abc123", None)
    assert code == 1
    return "\n".join(printed)


def test_admin_service_remedy_names_no_illegal_staging_target(monkeypatch):
    out = _refusal_output(monkeypatch, "admin-service")
    assert "admin-service-staging" not in out
    assert "_TARGET=admin-service," in out


def test_backend_remedy_still_suggests_the_staging_sibling(monkeypatch):
    out = _refusal_output(monkeypatch, "backend")
    assert "_TARGET=backend-staging," in out
