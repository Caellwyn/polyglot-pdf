"""Shared pytest fixtures for the backend test suite."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_confirmation_logs(tmp_path, monkeypatch):
    """Redirect confirmation-audit logs to a per-test tmp dir.

    The confirmation logger writes one JSONL file per form session
    (see backend/utils/confirmation_logger.py). Without this, any test that
    exercises field confirmation (e.g. test_section_switching) would append to
    the repo's real `logs/confirmations/` tree and dirty the working tree on
    every run. Pointing CONFIRMATION_LOG_DIR at tmp_path keeps tests hermetic
    and keeps real confirmation logs out of git.
    """
    monkeypatch.setenv("CONFIRMATION_LOG_DIR", str(tmp_path / "confirmations"))
