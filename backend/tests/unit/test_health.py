from fastapi.testclient import TestClient
from backend.main import app


client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    for key in ("models", "audio", "limits", "env"):
        assert key in body


def test_version_endpoint():
    r = client.get("/version")
    assert r.status_code == 200
    assert "version" in r.json()
