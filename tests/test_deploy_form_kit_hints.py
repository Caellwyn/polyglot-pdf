"""scripts/deploy-form-kit.sh's post-deploy hints must not be actively wrong
(bd polyglot-pdf-pnye).

Two hints went stale after bd polyglot-pdf-z2is:

1. `gcloud run services update ... --set-env-vars ...` REPLACES the whole env
   set, silently dropping CONFIRMATION_FIRESTORE_ENABLED, GOOGLE_CLOUD_PROJECT,
   and VERTEXAI (added under z2is) -- disabling the durable confirmation audit
   sink with no error if an operator follows the hint literally.
2. `curl https://your-backend-url/api/form-kits` (no auth) 401s unconditionally
   once that route became auth-gated (z2is), making a CORRECT deploy look
   broken.

These tests read the ACTUAL shipped script text, not a reimplementation, so a
regression to either stale hint fails here.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_KIT = REPO_ROOT / "scripts" / "deploy-form-kit.sh"


def _hint_text() -> str:
    return DEPLOY_KIT.read_text(encoding="utf-8")


def _gcloud_env_flag_invocation_lines(text: str) -> list[str]:
    """The line(s) that print the ACTUAL `gcloud ... --*-env-vars <vars>`
    invocation an operator would copy-paste -- i.e. the flag immediately
    followed by the FORM_KITS_MODE=... variable assignment -- excluding
    prose that merely MENTIONS the flag name to explain why it is wrong
    (e.g. "NOT --set-env-vars -- the latter REPLACES..."). That prose line
    legitimately contains the destructive flag's name as a warning; only the
    copy-pasteable command line is the thing this test must pin."""
    return [
        line for line in text.splitlines()
        if re.search(r'--(set|update)-env-vars\s+FORM_KITS_MODE=', line)
    ]


def test_the_env_var_hint_uses_update_not_set():
    lines = _gcloud_env_flag_invocation_lines(_hint_text())
    assert lines, "expected exactly one printed --*-env-vars invocation line"
    for line in lines:
        assert "--update-env-vars" in line, (
            f"printed invocation line uses the wrong flag (must be "
            f"--update-env-vars, a merge, not --set-env-vars, a replace-"
            f"the-whole-env-set): {line!r}"
        )
        assert "--set-env-vars" not in line


def test_the_drop_list_warning_names_every_deploy_env_var():
    """The warning that explains WHY --set-env-vars is destructive enumerates
    by name the vars it would silently drop. That enumeration must track the
    deploy env (bd polyglot-pdf-vccy added FIRMS_FIRESTORE_ENABLED to
    deploy-all.sh's BACKEND_ENV -- a drop of it silently hides every firm's
    private kits). Mutation: remove FIRMS_FIRESTORE_ENABLED from the hint's
    drop list -- red."""
    text = _hint_text()
    for var in (
        "CONFIRMATION_FIRESTORE_ENABLED",
        "FIRMS_FIRESTORE_ENABLED",
        "GOOGLE_CLOUD_PROJECT",
        "VERTEXAI",
    ):
        assert var in text, f"drop-list warning no longer names {var}"


def test_the_verify_hint_does_not_suggest_a_tokenless_curl():
    text = _hint_text()
    # The old hint literally embedded this exact tokenless curl -- if it
    # comes back, an operator following it gets a 401 that reads as a
    # broken deploy on a route that has been auth-gated since bd z2is.
    assert 'curl https://your-backend-url/api/form-kits' not in text
    # A working replacement must actually show HOW to authenticate the
    # request, not just gesture at "add a token somewhere".
    assert "Authorization: Bearer" in text
    assert "AUTH-GATED" in text or "auth-gated" in text.lower()


def test_the_env_var_hint_names_every_service_that_serves_the_bucket():
    """The hint must cover BOTH backends, not just the demo.

    Before bd polyglot-pdf-9qn64 there was one Cloud Run service, so a hint
    naming `polyglot-backend` was complete. There are now two running the same
    image against the same shared form-kits bucket, and an operator following a
    one-service hint updates only the demo's env, silently leaving staging's
    FORM_KITS_* untouched (bd polyglot-pdf-20940).

    Pinned as the SET, matching tests/test_deploy_reachability_gate.py's
    GATED_DEPLOY_SCRIPTS: a THIRD service added later must be added here too,
    rather than quietly dropping out of the advice.
    """
    text = _hint_text()
    services = {"polyglot-backend", "polyglot-backend-staging"}
    printed = {
        m.group(1)
        for line in _gcloud_env_flag_invocation_lines(text)
        for m in [re.search(r"gcloud run services update (\S+)", line)]
        if m
    }
    # The invocation and its flag are on separate printed lines, so recover the
    # service from the `gcloud run services update` line just above each.
    if not printed:
        printed = set(re.findall(r"gcloud run services update (\S+)", text))
    assert printed == services, (
        f"the env-var hint names {sorted(printed)}, expected {sorted(services)}. "
        f"Every service serving the shared form-kits bucket needs its env "
        f"updated; a hint that names only some teaches 'there is one backend'."
    )
