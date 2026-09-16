"""admin_backend.services.cloud_build.run_target (bd polyglot-pdf-tb3kp,
Epic 4 bead 4.3 of docs/sprint_22_admin-console_plan.md).

Pins the fresh-eyes/cross-surface review finding: run_target must pass the
`_SHA` substitution on the RunBuildTriggerRequest's RepoSource, not just
commit_sha. commit_sha alone tells Cloud Build which commit to check out;
it does NOT populate the `_SHA` substitution cloudbuild.yaml's own step 0
(require-sha) requires to be non-empty. Every trigger this module runs is
provisioned (scripts/setup-cloud-build.sh) with only `_TARGET`/`_CHANNEL`
substitutions -- `_SHA` defaults to an empty string in cloudbuild.yaml and
must be supplied per-run, exactly as the documented human invocation does
("gcloud builds triggers run ... --sha=<sha> --substitutions=_SHA=<sha>").

Without the substitution, every console-triggered build would abort at
cloudbuild.yaml's step 0 with "ABORT: _SHA is empty" -- while this route
had already returned 200 with a real build_id and a "queued" deployments
row. The route's own tests (test_deploy_routes.py) mock run_target
entirely and cannot catch this; this file is the one place that exercises
the actual request shape run_target builds.

Mutation-verified: reverting the `substitutions={"_SHA": sha}` kwarg (back
to a bare `commit_sha=sha` RepoSource) is what proves
test_run_target_passes_the_sha_substitution can fail.

ASCII only.
"""
from __future__ import annotations

import pytest

from admin_backend.services import cloud_build


class _FakeOperation:
    def __init__(self, build_id, log_url):
        class _Meta:
            def __init__(self, build):
                self.build = build

        class _Build:
            def __init__(self, id_, log_url):
                self.id = id_
                self.log_url = log_url

        self.metadata = _Meta(_Build(build_id, log_url))


class _FakeClient:
    """Captures the RunBuildTriggerRequest run_target builds, instead of
    making a real RPC. Constructed in place of cloud_build._client()."""

    def __init__(self):
        self.requests = []

    def run_build_trigger(self, request):
        self.requests.append(request)
        return _FakeOperation(build_id="build-999", log_url="https://log/999")


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(cloud_build, "_client", lambda *, region: client)
    return client


def test_run_target_passes_the_sha_substitution(fake_client):
    sha = "a" * 40

    result = cloud_build.run_target(
        "editor", sha, project_id="proj-1", region="us-central1")

    assert result == {"build_id": "build-999", "log_url": "https://log/999"}
    assert len(fake_client.requests) == 1
    request = fake_client.requests[0]
    assert request.source.commit_sha == sha
    # THE PINNED ASSERTION: the _SHA substitution must be set on the
    # RepoSource, matching what the trigger's own cloudbuild.yaml step 0
    # requires to be non-empty. Reverting the substitutions kwarg makes
    # this assertion fail (mutation-verified).
    assert dict(request.source.substitutions) == {"_SHA": sha}


def test_run_target_names_the_trigger_and_project(fake_client):
    sha = "b" * 40

    cloud_build.run_target(
        "backend-staging", sha, project_id="proj-2", region="us-central1")

    request = fake_client.requests[0]
    assert request.project_id == "proj-2"
    assert request.trigger_id == "polyglot-backend-staging"


def test_run_target_addresses_the_trigger_regionally(fake_client):
    """The REGIONAL name, not just project_id/trigger_id.

    The REST transport tries its URI templates in order and the
    project/trigger pair alone matches the GLOBAL-only
    "/v1/projects/{project_id}/triggers/{trigger_id}:run" template first --
    so without `name` every run addresses the global trigger registry,
    whatever endpoint the client was built for, and 404s: every trigger this
    repo provisions is regional (scripts/setup-cloud-build.sh's "REGION IS
    NOT OPTIONAL").
    """
    sha = "c" * 40

    cloud_build.run_target(
        "admin-service", sha, project_id="proj-3", region="europe-west1")

    request = fake_client.requests[0]
    assert request.name == (
        "projects/proj-3/locations/europe-west1/triggers/polyglot-admin-service"
    ), "the request must carry the regional trigger resource name"


def test_run_target_wraps_a_client_failure(monkeypatch):
    def _boom(*, region):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(cloud_build, "_client", _boom)

    with pytest.raises(cloud_build.CloudBuildUnavailable):
        cloud_build.run_target(
            "editor", "c" * 40, project_id="proj-3", region="us-central1")
