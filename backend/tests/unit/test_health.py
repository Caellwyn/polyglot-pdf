import pytest
from fastapi.testclient import TestClient

import backend.main as main
import backend.services.firms as firms
from backend.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_firms_probe_cache():
    """The firms probe caches process-wide; clear it around every test here.

    Without this, whichever test runs first pins the answer for the rest and
    the later assertions describe a stale value rather than the branch they
    name.
    """
    firms._probe_cache = None
    firms._probe_in_flight = None
    yield
    firms._probe_cache = None
    firms._probe_in_flight = None


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_health_discloses_nothing_but_status_and_the_probes():
    """/health is unauthenticated; it must not fingerprint the deployment
    (sprint 23 B1b, PF-10): no model id, audio rate, upload limit, provider
    flag or key-presence bit. EXACT key set, so a new field fails here
    rather than shipping silently. Mutation: add "models" back -- red."""
    body = client.get("/health").json()
    assert set(body) == {"status", "confirmation_sink", "firms_store"}, sorted(body)
    flat = repr(body).lower()
    for banned in ("gemini", "model", "rate", "upload", "vertex", "api_key", "chunk"):
        assert banned not in flat, banned


def test_version_endpoint():
    r = client.get("/version")
    assert r.status_code == 200
    assert "version" in r.json()


# ---------------------------------------------------------------------------
# Firms store probe on /health (bd polyglot-pdf-vq5wd / polyglot-pdf-e4dt8)
# ---------------------------------------------------------------------------


def test_health_reports_the_firms_store_probe(monkeypatch):
    """/health carries the firms-store READ probe alongside the sink probe.

    The failure this guards is invisible otherwise: under IAM drift the firms
    read fails closed, every firm's private kits vanish, and the app keeps
    answering 200 with no signal anywhere. Mutation: drop the firms_store key
    from the response dict -- red.
    """
    monkeypatch.setattr(main, "firms_store_status", lambda: "ok")
    body = client.get("/health").json()
    assert body["firms_store"] == "ok"


def test_health_surfaces_a_firms_probe_error_verbatim(monkeypatch):
    """A failing probe REACHES the response; it is not swallowed into "ok".

    Pinning the error branch specifically, because a handler that caught the
    failure and reported "ok" would pass the happy-path test above while
    hiding the exact outage the probe exists to detect.
    """
    monkeypatch.setattr(
        main, "firms_store_status", lambda: "error: iam drift")
    body = client.get("/health").json()
    assert body["firms_store"] == "error: iam drift"
    # The endpoint itself still answers 200: /health reporting a component's
    # status is not /health failing, and the uptime checks must keep passing
    # so an ALERT (not a flapping uptime check) is what pages.
    assert body["status"] == "ok"


def test_health_bounds_a_stalled_firms_probe(monkeypatch):
    """A hung firms store cannot hang /health.

    /health is unauthenticated and is what the per-channel uptime checks poll
    (scripts/setup-monitoring.sh). Without the wait_for, a stalled Firestore
    turns every uptime check into a timeout and the alerting goes dark exactly
    when it is needed. Mutation: remove the asyncio.wait_for around the firms
    probe -- this test reports "ok" instead of the timeout string.
    """
    # Sleeps a little longer than the patched 0.2s budget below. The
    # ORIGINAL version slept 30s against the real 3.0s budget and cost
    # ~30s of wall clock per test -- asyncio.wait_for does not CANCEL an
    # asyncio.to_thread worker on timeout, it only stops awaiting it, so
    # the suite still waited out the whole sleep. Same property, 1% of
    # the runtime.
    def _hang():
        import time
        time.sleep(1.0)
        return "ok"

    monkeypatch.setattr(main, "firms_store_status", _hang)
    monkeypatch.setattr(main, "HEALTH_PROBE_TIMEOUT_S", 0.2)
    body = client.get("/health").json()
    assert body["firms_store"] == "error: probe timed out"


def test_the_two_probes_have_independent_budgets(monkeypatch):
    """A stalled firms probe must not consume the sink probe's answer.

    They are awaited in sequence with a wait_for each, not under one shared
    deadline -- so one component being down still leaves the other's status
    readable, which is the whole point of reporting them separately.
    """
    # Sleeps a little longer than the patched 0.2s budget below. The
    # ORIGINAL version slept 30s against the real 3.0s budget and cost
    # ~30s of wall clock per test -- asyncio.wait_for does not CANCEL an
    # asyncio.to_thread worker on timeout, it only stops awaiting it, so
    # the suite still waited out the whole sleep. Same property, 1% of
    # the runtime.
    def _hang():
        import time
        time.sleep(1.0)
        return "ok"

    monkeypatch.setattr(main, "firms_store_status", _hang)
    monkeypatch.setattr(main, "HEALTH_PROBE_TIMEOUT_S", 0.2)
    monkeypatch.setattr(main, "confirmation_sink_status", lambda: "ok")

    body = client.get("/health").json()
    assert body["firms_store"] == "error: probe timed out"
    assert body["confirmation_sink"] == "ok", (
        "the confirmation sink's status was lost to the firms probe's stall")
