"""GET /version returns the deployed commit SHA (bd polyglot-pdf-9hzod).

Epic 1 child 1.6. GIT_SHA is a runtime env var the deploy bridge sets via
`--set-env-vars GIT_SHA=$(git rev-parse HEAD)` (bead 1.3, not this bead) --
here we only pin what the route itself does with the env var: report it
when set, and report "unknown" (not a KeyError, not a blank string) when
it is absent, since the admin console's "what is live per channel" view
(bead 1.7) needs a renderable value either way.
"""
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_version_reports_the_git_sha_when_set(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234def5678")
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["git_sha"] == "abc1234def5678"
    assert body["version"] == app.version


def test_version_reports_unknown_when_git_sha_is_unset(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["git_sha"] == "unknown"


def test_version_reports_unknown_when_git_sha_is_empty(monkeypatch):
    """An empty (but SET) GIT_SHA is the same defensive-default shape the
    Dockerfile's `${APP_MODULE:-...}` handles for APP_MODULE
    (docs/components/config-deployment.md, "One image, two services"): a
    `--set-env-vars` block can pass a variable as empty. `os.getenv` alone
    would return "" here rather than falling back, so this pins the `or`
    fallback explicitly rather than relying on the unset case alone to prove
    it.
    """
    monkeypatch.setenv("GIT_SHA", "")
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["git_sha"] == "unknown"
