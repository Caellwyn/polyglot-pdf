"""cloudbuild.yaml is the ONE build definition every deploy target runs through.

bd polyglot-pdf-1s3ko (Epic 4 of docs/sprint_22_admin-console_plan.md). The
build file is data, so the things that must be true about it are checked here
rather than discovered in a failed build minutes after a deploy starts:

  - the three substitution names the wrappers and the admin service pass;
  - the verify target running all THREE suites, not the one someone remembers;
  - the build_checks gate being the FIRST real step of every DEPLOY target --
    the property that makes "five targets, one test run" safe;
  - the backend target taking its env from deploy/channels/<channel>.env
    rather than restating it, which is the whole reason those files exist.

The gate is the assertion that matters most. Without it a commit whose suites
failed deploys normally, and the build_checks record becomes decoration.
"""

from __future__ import annotations

import configparser
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

yaml = pytest.importorskip(
    "yaml",
    reason=(
        "PyYAML is a transitive dependency of uvicorn[standard], which "
        "backend/requirements.txt pins -- so CI always has it. Skipping "
        "rather than erroring keeps a bare local interpreter usable."
    ),
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CLOUDBUILD = REPO_ROOT / "cloudbuild.yaml"
CHANNELS = REPO_ROOT / "deploy" / "channels"

# The targets cloudbuild.yaml implements end to end in THIS bead. Every other
# name in the substitution comment is bead polyglot-pdf-ywxoh's (4.2).
IMPLEMENTED_TARGETS = ("verify", "backend-staging", "backend-demo")
DEPLOY_TARGETS = ("backend-staging", "backend-demo")


def _testpaths() -> list[str]:
    """The declared suite roots, read from pytest.ini itself.

    Derived, never hand-listed -- a copied expectation here drifts the same way
    a hardcoded pytest command line does (CLAUDE.md scar #8).
    """
    parser = configparser.ConfigParser()
    parser.read_string(
        io.open(REPO_ROOT / "pytest.ini", encoding="utf-8").read())
    raw = parser.get("pytest", "testpaths")
    return [line.strip().rstrip("/") for line in raw.splitlines() if line.strip()]


def _whole_suite_arg_pattern(root: str) -> str:
    r"""Match a suite root used as a WHOLE argument, nothing deeper.

    A DEEPER path (backend/tests/unit) would be a deliberately narrow run; only
    the bare root claims to be the full suite while excluding its siblings.
    """
    return (r"(?:^|[\s\"'`=])(?:\$\{?\w+\}?/|\./|/)?"
            + re.escape(root) + r"/?(?=[\s\"'`]|$)")


@pytest.fixture(scope="module")
def build() -> dict:
    return yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(build) -> list[dict]:
    return build["steps"]


@pytest.fixture(scope="module")
def by_id(steps) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for step in steps:
        sid = step.get("id")
        assert sid, f"every step needs an id; {step.get('name')} has none"
        assert sid not in out, f"duplicate step id {sid}"
        out[sid] = step
    return out


def script_of(step: dict) -> str:
    """The bash body of a step: the last arg after `bash -c`."""
    return step["args"][-1]


def test_the_file_parses_and_has_steps(build, steps):
    """Guard the guard: an empty parse would satisfy every `not in` below."""
    assert len(steps) >= 8, f"only {len(steps)} steps parsed"


def test_the_substitution_names_are_pinned(build):
    """The wrappers, setup-cloud-build.sh and the admin service all pass these.

    Renaming one silently drops it to its default in every caller -- and a
    dropped _SHA is a gate that vouches for the wrong commit.
    """
    subs = build["substitutions"]
    assert set(subs) == {"_TARGET", "_CHANNEL", "_SHA"}, (
        f"cloudbuild.yaml declares {sorted(subs)}; the callers pass exactly "
        "_TARGET, _CHANNEL and _SHA"
    )
    assert subs["_SHA"] == "", (
        "_SHA must default EMPTY so the require-sha step can refuse a build "
        "that did not name a commit -- a non-empty default would let every "
        "unspecified build share one record"
    )


def test_an_empty_sha_is_refused_before_anything_else(steps):
    """ONE empty-SHA verify would otherwise vouch for every empty-SHA deploy."""
    first = steps[0]
    body = script_of(first)
    assert 'if [ -z "${_SHA}" ]; then' in body, (
        f"the FIRST step ({first['id']}) does not refuse an empty _SHA; it is "
        f"{body[:200]!r}"
    )
    assert "exit 1" in body


def test_every_suite_the_plan_names_runs_in_the_verify_target(by_id):
    """Every suite, not the ones someone remembers.

    The plan names backend + frontend + admin-console. A verify build that
    runs two of them still writes a success record, so every deploy target for
    that SHA proceeds on a partial test run.

    The python half asserts the ABSENCE of suite paths rather than the
    presence of today's three: a hardcoded list is exactly the drift bd
    polyglot-pdf-3ave and bd polyglot-pdf-pnoik shipped, and a test that
    pinned the list would bless it. The set pin for that property across all
    three gates lives in tests/test_every_suite_root_is_gated.py; this asserts
    the local shape of the step.
    """
    backend = script_of(by_id["verify-backend"])
    assert "python -m pytest" in backend
    # Only the invocation LINES, never the comments above them: the comment
    # explaining why the roots are absent names them, and a scan that read it
    # would fail on the fixed file (and pass on a file whose comment was
    # deleted) -- guarding prose instead of the command.
    commands = [line for line in backend.splitlines()
                if "pytest" in line and not line.lstrip().startswith("#")]
    assert commands, "the verify step has no pytest command line"
    named = sorted({root for root in _testpaths() for line in commands
                    if re.search(_whole_suite_arg_pattern(root), line)})
    assert not named, (
        "the verify step names suite paths {!r}, so a new pytest.ini testpaths "
        "root would not run in the gate that writes build_checks/{{sha}}; use a "
        "bare `python -m pytest` and let testpaths decide".format(named)
    )
    assert '-m "not external"' in backend, (
        "the verify run must exclude the flaky live-Gemini externals, matching "
        "CI -- those need real credentials the build does not have"
    )

    frontend = script_of(by_id["verify-frontend"])
    assert "cd frontend" in frontend and "npm run test:run" in frontend
    assert "npm ci" in frontend

    console = script_of(by_id["verify-admin-console"])
    assert "cd admin-console" in console and "npm run test:run" in console
    assert "npm ci" in console


def test_the_verify_target_records_its_result(by_id):
    """A gate nothing writes to refuses every deploy forever."""
    body = script_of(by_id["record-build-check"])
    assert "record_build_check.py record" in body
    assert "--status success" in body
    assert "${_SHA}" in body
    assert "$BUILD_ID" in body, (
        "the record must carry the build id, so a later deploy can be traced "
        "to the build that vouched for it"
    )


def test_node_22_matches_ci(steps):
    """A suite passing in CI must be running the same runtime here."""
    node_steps = [s for s in steps if str(s.get("name", "")).startswith("node:")]
    assert node_steps, "no node step found in cloudbuild.yaml"
    for step in node_steps:
        assert step["name"] == "node:22", (
            f"step {step['id']} runs {step['name']}; .github/workflows/ci.yml "
            "pins node-version 22"
        )


def test_the_build_checks_gate_precedes_every_deploy_step(steps, by_id):
    """THE CRITERION: no deploy work may run before the gate.

    Cloud Build runs steps in order unless waitFor says otherwise, so the
    gate's protection is positional: its index must be lower than the index of
    every step that builds, pushes or deploys anything. Asserting only that a
    gate step EXISTS would pass with the gate moved after the deploy, which is
    no gate at all.

    The step list is walked rather than named, so a deploy step added later
    cannot slip in above the gate unnoticed.
    """
    order = {step["id"]: i for i, step in enumerate(steps)}
    assert "gate-build-checks" in order, "no build_checks gate step at all"
    gate = order["gate-build-checks"]

    mutating = []
    for step in steps:
        if step["id"] == "gate-build-checks":
            continue
        body = script_of(step)
        if any(
            token in body
            for token in ("gcloud run deploy", "docker push", "firebase deploy")
        ):
            mutating.append(step["id"])

    assert mutating, (
        "no step in cloudbuild.yaml deploys anything, so this guard would "
        "pass vacuously -- the extractor has drifted from the file"
    )
    for sid in mutating:
        assert order[sid] > gate, (
            f"step {sid} deploys or pushes at index {order[sid]}, BEFORE the "
            f"build_checks gate at index {gate}. A commit whose suites failed "
            "would ship."
        )


def test_the_gate_requires_a_record_and_is_a_no_op_only_for_verify(by_id):
    """The gate must REFUSE, and must exempt exactly one target.

    Exempting anything but `verify` would let that target deploy ungated.
    """
    body = script_of(by_id["gate-build-checks"])
    assert "record_build_check.py require" in body, (
        "the gate step does not call the require subcommand, so it checks "
        "nothing"
    )
    assert "${_SHA}" in body, "the gate does not read the SHA it is gating"
    assert 'if [ "${_TARGET}" = "verify" ]; then' in body, (
        "the gate's only exemption must be the verify target itself -- that is "
        "the build that CREATES the record"
    )


@pytest.mark.parametrize("target", DEPLOY_TARGETS)
def test_the_backend_target_takes_its_env_from_the_channel_file(by_id, target):
    """The reason deploy/channels/ exists.

    A Cloud Build step cannot read a bash string, so before the channel files
    the build would have had to RESTATE what deploy-staging.sh set -- and a
    restated config is the drift tests/test_deploy_channel_parity.py exists to
    catch, reintroduced at a second site.
    """
    body = script_of(by_id["backend-deploy"])
    assert "deploy/channels/${_CHANNEL}.env" in body, (
        "the backend target does not read the channel file, so its env is "
        "restated somewhere instead of sourced"
    )
    # Every section must be consumed, not just the env one: a secret binding
    # or runtime SA read from the file and never forwarded is the classic
    # "documented but never passed" defect (bd polyglot-pdf-hvui4).
    assert "read_channel_section" in body
    assert "SET_ENV_VARS" in body and "SET_SECRETS" in body
    assert "read_channel_value" in body and "SERVICE_ACCOUNT" in body
    assert '--set-env-vars="$$BACKEND_ENV"' in body
    assert '"$${SECRETS_FLAG[@]}"' in body
    assert '"$${SA_FLAG[@]}"' in body
    # The channel values must actually be appended, not merely read.
    assert 'BACKEND_ENV="$$BACKEND_ENV,$$CHANNEL_ENV"' in body


def test_the_backend_target_refuses_an_empty_channel_env(by_id):
    """deploy-all.sh's refusal has to travel to the second consumer.

    --set-env-vars REPLACES the service's env block, so a channel file whose
    [SET_ENV_VARS] section is present but EMPTY deploys the computed defaults
    alone: VERTEXAI, every LINK_* key and CORS_EXTRA_ORIGINS silently vanish
    from the running service. deploy-all.sh:582 refuses that (pinned by
    tests/test_deploy_channel_parity.py); this step reads the SAME file
    through the SAME parser, so the same refusal must precede the append --
    the missing-FILE case aborts on its own via set -e, the empty-SECTION case
    does not.
    """
    body = script_of(by_id["backend-deploy"])
    refusal = body.find('if [ -z "$$CHANNEL_ENV" ]; then')
    assert refusal != -1, (
        "the backend deploy step does not refuse an empty [SET_ENV_VARS]; it "
        "would deploy with every channel setting stripped off the service"
    )
    # PIN THE ARM, NOT THE FILE: `"exit 1" in body` passes with this branch
    # flipped to exit 0, because the unknown-channel case below carries one.
    arm = body[refusal:body.index("case \"${_CHANNEL}\" in", refusal)]
    assert "exit 1" in arm, (
        "the empty-[SET_ENV_VARS] branch does not exit non-zero, so the build "
        "continues into the deploy:\n" + arm
    )
    # It must come BEFORE the append, or it guards nothing.
    assert refusal < body.index('BACKEND_ENV="$$BACKEND_ENV,$$CHANNEL_ENV"'), (
        "the refusal follows the append, so the stripped env is already built"
    )


def test_the_backend_target_records_the_built_commit(by_id):
    """GIT_SHA is what GET /version reports.

    Passing anything but the SHA the gate vouched for would make the deployed
    service claim a commit it is not running (bd polyglot-pdf-3l2vp).
    """
    body = script_of(by_id["backend-deploy"])
    assert "GIT_SHA=${_SHA}" in body, (
        "the backend deploy does not set GIT_SHA from the gated _SHA"
    )
    assert "APP_MODULE=" in body, (
        "the backend deploy does not set APP_MODULE, so the one shared image "
        "would fall back to its Dockerfile default rather than declaring it"
    )
    assert "polyglot-backend:${_SHA}" in body, (
        "the deployed image tag must be the gated commit, not :latest -- a "
        "floating tag deploys whatever was pushed last"
    )


def test_every_unimplemented_target_fails_loudly(by_id):
    """A target that matches no step builds nothing and reports SUCCESS.

    The admin console would then record a green deploy that deployed nothing,
    which is worse than an error.
    """
    body = script_of(by_id["unimplemented-targets"])
    # PIN THE ARM, NOT THE FILE. Asserting `"exit 1" in body` passed with the
    # not-implemented arm flipped to `exit 0`, because the unknown-target arm
    # further down still carried an `exit 1`. Read the line that FOLLOWS the
    # message instead, so the arm that matters is the one under test.
    lines = [line.strip() for line in body.splitlines()]
    assert "echo \"target not implemented\"" in lines, (
        "the not-implemented arm does not announce itself"
    )
    after = lines[lines.index("echo \"target not implemented\"") + 1]
    assert after == "exit 1", (
        f"the not-implemented arm continues with {after!r}, not `exit 1`. A "
        "target that builds nothing must FAIL -- exiting 0 makes the admin "
        "console record a green deploy that deployed nothing."
    )
    for target in IMPLEMENTED_TARGETS:
        assert target in body, (
            f"{target} is implemented but is not in the pass-through arm, so "
            "a real build would be refused"
        )
    assert "ABORT: unknown target" in body, (
        "an unrecognised target name must abort rather than fall through"
    )


def test_every_channel_named_by_a_target_has_a_file(by_id):
    """A target whose channel file is missing fails minutes into a build."""
    body = script_of(by_id["backend-deploy"])
    for channel in ("staging", "demo"):
        assert f"{channel})" in body, (
            f"the backend target maps no service for channel {channel}"
        )
        assert (CHANNELS / f"{channel}.env").is_file(), (
            f"deploy/channels/{channel}.env does not exist"
        )
    assert (CHANNELS / "admin.env").is_file()


def test_every_step_script_is_valid_bash(steps):
    """A syntax error in an inline script fails minutes into a real build.

    YAML block scalars swallow shell quoting problems silently -- the file
    parses, the step is well-formed, and bash rejects it only when it runs.
    """
    # shutil.which, never a bare "bash": on Windows a bare name resolves to
    # WSL's bash, which cannot see the Git-Bash filesystem and fails every
    # script with a relay error that reads like a syntax error (mirrors
    # tests/test_deploy_reachability_gate.py).
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover
        pytest.skip("bash not on PATH")
    for step in steps:
        script = script_of(step)
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".sh", delete=False, newline="\n", encoding="utf-8"
        )
        handle.write(script)
        handle.close()
        try:
            result = subprocess.run(
                [bash, "-n", handle.name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        finally:
            os.unlink(handle.name)
        assert result.returncode == 0, (
            f"step {step['id']} is not valid bash:\n{result.stderr}"
        )


def test_the_file_is_ascii():
    """CLAUDE.md scar 6, applied to the build definition.

    A smart quote or em-dash here reaches a shell inside a container and, on
    the Windows side, a cp1252 console that cannot decode it.
    """
    raw = CLOUDBUILD.read_bytes()
    try:
        raw.decode("ascii")
    except UnicodeDecodeError as exc:
        pytest.fail(f"cloudbuild.yaml is not ASCII at byte {exc.start}")


# ---------------------------------------------------------------------------
# scripts/setup-cloud-build.sh -- the provisioning half.
# ---------------------------------------------------------------------------

SETUP = REPO_ROOT / "scripts" / "setup-cloud-build.sh"


def _strip_shell_comment(line: str) -> str:
    """The executable part of a shell line, quoting-aware."""
    out: list[str] = []
    quote: str | None = None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        out.append(ch)
    return "".join(out)


def _setup_live_text() -> str:
    """scripts/setup-cloud-build.sh with comments removed.

    The header documents the flags it deliberately does NOT pass, so a
    whole-file substring check would read the explanation as the flag.
    """
    return "\n".join(
        _strip_shell_comment(line)
        for line in SETUP.read_text(encoding="utf-8").splitlines()
    )


def _trigger_create_argv(live: str) -> list[str]:
    """The argument lines of the `gcloud builds triggers create` invocation.

    The script builds it as a bash ARRAY spanning several lines, so slice from
    the array open to its closing paren. Being NEAR the invocation is not
    being IN it -- the same containment-vs-proximity error
    tests/test_deploy_channel_parity.py's argv parser exists to avoid.
    """
    lines = live.splitlines()
    start = next(
        (i for i, l in enumerate(lines) if "builds triggers create" in l), None
    )
    if start is None:
        return []
    argv: list[str] = []
    for line in lines[start:]:
        argv.append(line.strip())
        if line.rstrip().endswith(")"):
            break
    return argv


def _parse_env_section(path) -> dict[str, str]:
    """The SET_ENV_VARS pairs of a channel file.

    A local minimal parser rather than an import from the sibling suite: test
    modules are not a package here, so a cross-module import depends on
    pytest's sys.path insertion and breaks under a different rootdir.
    """
    pairs: dict[str, str] = {}
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            continue
        if current == "SET_ENV_VARS" and "=" in line:
            key, _, value = line.partition("=")
            pairs[key] = value
    assert pairs, f"{path.name} parsed to no SET_ENV_VARS pairs"
    return pairs


def test_the_trigger_script_names_a_trigger_for_every_target(by_id):
    """A target with no trigger cannot be run, which is a silent gap.

    Derived from cloudbuild.yaml's own target list rather than restated: a
    hand-typed second list is the drift this whole bead is about.
    """
    setup = SETUP.read_text(encoding="utf-8")
    body = script_of(by_id["unimplemented-targets"])
    # The names cloudbuild.yaml knows: the implemented arm plus the
    # not-implemented arm, both spelled as case patterns.
    declared = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.endswith(")") and "|" in stripped:
            for name in stripped.rstrip(")").split("|"):
                name = name.strip()
                if name and name.replace("-", "").isalnum():
                    declared.add(name)
    assert len(declared) >= 10, (
        f"only parsed {sorted(declared)} out of cloudbuild.yaml, so this "
        "guard would pass vacuously"
    )
    for target in sorted(declared):
        assert f'"{target}:' in setup, (
            f"scripts/setup-cloud-build.sh creates no trigger for target "
            f"{target}, so it can never be run"
        )


def test_the_trigger_script_uses_the_2nd_gen_repository_flag():
    """--repository and --repo/--repo-type are MUTUALLY EXCLUSIVE.

    Passing both is rejected by the CLI, not ignored, so a script carrying the
    1st-gen pair alongside the 2nd-gen resource creates no triggers at all.
    """
    live = _setup_live_text()
    assert "--repository=" in live, (
        "the private repo needs the 2nd-generation connected-repository "
        "resource; nothing else can fetch an arbitrary commit"
    )
    # LIVE lines only: the header explains WHY the 1st-gen pair is absent, and
    # a whole-file check would read that explanation as the flag itself.
    assert "--repo-type=" not in live, (
        "--repo-type is the 1st-gen flag and is mutually exclusive with "
        "--repository; gcloud rejects the pair"
    )


def test_the_trigger_script_pins_a_region():
    """A 2nd-gen repository cannot live in global.

    Omitting --region resolves to the builds/region property or global, and
    the trigger is then simply not found -- which reads as a missing trigger
    rather than a wrong region.
    """
    live = _setup_live_text()
    # PIN THE CREATE INVOCATION, NOT THE FILE. A whole-file `--region=` check
    # passed with the flag deleted from the trigger-create argv, because the
    # closing echo that tells the operator how to RUN a trigger still mentions
    # it -- a region on the instructions and none on the creation.
    create = _trigger_create_argv(live)
    assert create, "could not locate the triggers create invocation"
    assert any("--region=" in arg for arg in create), (
        "scripts/setup-cloud-build.sh creates triggers without --region. A "
        "2nd-gen repository cannot live in global, so the triggers land "
        f"nowhere findable. Parsed argv: {create}"
    )
    assert any("CLOUD_BUILD_REGION" in arg for arg in create), (
        "the region must come from the named variable, not a repeated "
        "literal, so the create and run commands cannot disagree"
    )


def test_the_trigger_script_points_at_this_build_file():
    setup = SETUP.read_text(encoding="utf-8")
    assert "cloudbuild.yaml" in setup
    assert "--build-config=" in setup


def test_admin_env_is_the_only_copy_of_the_admin_service_config(by_id):
    """deploy-admin.sh must NOT restate what deploy/channels/admin.env says.

    This replaces the temporary guard that pinned the file and the wrapper
    EQUAL while both carried the same values -- that duplication ended when
    deploy-admin.sh became a thin Cloud Build wrapper (bd polyglot-pdf-oqtm7,
    4.6), which is exactly when its own docstring said this guard should go.
    What is worth pinning now is the opposite property: one source. A wrapper
    that started setting env vars again would be a second live copy, and the
    build's --set-env-vars REPLACES the whole block, so whichever path ran
    last would silently win.
    """
    admin = _parse_env_section(CHANNELS / "admin.env")
    wrapper = (REPO_ROOT / "deploy-admin.sh").read_text(encoding="utf-8")
    for key in admin:
        assert f"{key}=" not in wrapper, (
            f"deploy-admin.sh assigns {key} again -- deploy/channels/admin.env "
            "is the one source the build reads, and two live copies of one "
            "config is the drift the channel files exist to end"
        )
    # And the build DOES read the file, so the values are not merely declared.
    body = script_of(by_id["admin-service-deploy-tagged"])
    assert "deploy/channels/admin.env" in body
    assert "read_channel_section" in body


def test_admin_service_deploy_tagged_env_set_is_complete(by_id):
    """(Not in the original handoff, cross-surface review round: bd
    polyglot-pdf-ywxoh.) admin.env's own [SET_ENV_VARS] comment says
    ADMIN_SERVICE_URL and BACKEND_URLS_JSON are DELIBERATELY absent from the
    file because they need a live gcloud lookup -- this step resolves them
    and appends them itself, precisely because --set-env-vars REPLACES the
    service's entire env block. Pin the COMPLETE set this Cloud Build step
    must assemble, not just the keys
    test_admin_env_is_the_only_copy_of_the_admin_service_config reads out of
    admin.env -- a step that silently drops any of these keys disables the
    refund sweep's OIDC audience
    (admin_backend/routes/sweep_routes.py::_audience), blanks
    GET /admin/health's channel fan-out
    (admin_backend/routes/ops_routes.py::_backend_urls), or (FORM_KITS_MODE/
    FORM_KITS_GCS_BUCKET/FORM_KITS_REMOTE_PREFIX -- a second cross-surface
    review round on the same bead) makes get_form_kit_store()
    (backend/services/form_kits.py) fall back to FORM_KITS_MODE's "local"
    default so GET /admin/kits (admin_backend/routes/kit_routes.py) silently
    returns an empty kit list -- all with a green build and no alert
    (CLAUDE.md scar #8: pin the set, not the instance).
    """
    body = script_of(by_id["admin-service-deploy-tagged"])
    for var in (
        "ADMIN_SERVICE_URL",
        "BACKEND_URLS_JSON",
        "FORM_KITS_MODE",
        "FORM_KITS_GCS_BUCKET",
        "FORM_KITS_REMOTE_PREFIX",
    ):
        assert var in body, (
            f"admin-service-deploy-tagged never mentions {var} -- it will "
            "be silently absent from the deployed service's env block, "
            "wiping whatever an earlier deploy-admin.sh run had set"
        )
    # Both live lookups must run BEFORE the gcloud run deploy that consumes
    # them, and their resolved values must actually reach --set-env-vars
    # (not merely appear somewhere in the script, e.g. only in a comment).
    deploy_idx = body.rindex("gcloud run deploy polyglot-admin")
    admin_url_idx = body.find("ADMIN_SERVICE_URL=$(gcloud run services describe")
    backend_urls_idx = body.find("BACKEND_URLS_PARTS=")
    form_kits_mode_idx = body.find("FORM_KITS_MODE=gcs")
    form_kits_bucket_idx = body.find("FORM_KITS_GCS_BUCKET=")
    form_kits_prefix_idx = body.find("FORM_KITS_REMOTE_PREFIX=")
    assert 0 <= admin_url_idx < deploy_idx, (
        "ADMIN_SERVICE_URL is not resolved via a live gcloud lookup before "
        "the gcloud run deploy call"
    )
    assert 0 <= backend_urls_idx < deploy_idx, (
        "BACKEND_URLS_JSON's parts are not assembled before the gcloud run "
        "deploy call"
    )
    assert 0 <= form_kits_mode_idx < deploy_idx, (
        "FORM_KITS_MODE is not assembled before the gcloud run deploy call"
    )
    assert 0 <= form_kits_bucket_idx < deploy_idx, (
        "FORM_KITS_GCS_BUCKET is not assembled before the gcloud run deploy call"
    )
    assert 0 <= form_kits_prefix_idx < deploy_idx, (
        "FORM_KITS_REMOTE_PREFIX is not assembled before the gcloud run deploy call"
    )
    set_env_vars_idx = body.index('--set-env-vars="$$BACKEND_ENV"')
    assert admin_url_idx < set_env_vars_idx and backend_urls_idx < set_env_vars_idx
    assert form_kits_mode_idx < set_env_vars_idx
    assert form_kits_bucket_idx < set_env_vars_idx
    assert form_kits_prefix_idx < set_env_vars_idx
    # The values themselves must match backend-deploy's exact computation
    # (cloudbuild.yaml's backend-deploy step / deploy-all.sh:509), not just
    # the variable names -- a step could mention FORM_KITS_GCS_BUCKET while
    # pointing it at the wrong bucket.
    assert "FORM_KITS_GCS_BUCKET=$PROJECT_ID-form-kits" in body
    assert "FORM_KITS_REMOTE_PREFIX=form-kits" in body


def test_admin_service_deploy_tagged_actually_passes_live_urls_at_runtime(tmp_path, by_id):
    """RUNTIME half of the test above: proves the resolved URLs actually
    reach the `gcloud run deploy` invocation's --set-env-vars string, not
    merely that the variable names appear in the source text. Stubs gcloud
    to answer `run services describe` with canned per-service URLs and
    captures the full argv of the final `run deploy` call.
    """
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover
        pytest.skip("bash not on PATH")

    script = script_of(by_id["admin-service-deploy-tagged"])
    rendered = (
        script.replace("${_TARGET}", "admin-service")
        .replace("${_SHA}", "deadbeef")
        .replace("$$", "$")
    )

    marker = tmp_path / "deploy_argv.txt"
    fake_gcloud = tmp_path / "gcloud"
    fake_gcloud.write_text(
        "#!/bin/bash\n"
        "if [ \"$1 $2\" = \"run services\" ] && [ \"$3\" = \"describe\" ]; then\n"
        "  case \"$4\" in\n"
        "    polyglot-admin) echo 'https://polyglot-admin-fake.a.run.app' ;;\n"
        "    polyglot-backend) echo 'https://polyglot-backend-fake.a.run.app' ;;\n"
        "    polyglot-backend-staging) echo 'https://polyglot-backend-staging-fake.a.run.app' ;;\n"
        "    *) exit 1 ;;\n"
        "  esac\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1 $2\" = \"run deploy\" ]; then\n"
        f'  echo "$@" > "{marker.as_posix()}"\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8", newline="\n",
    )
    fake_gcloud.chmod(0o755)

    # A Windows-drive-letter PATH entry ("C:/...", what tmp_path.as_posix()
    # produces) is NOT resolved by Git Bash's PATH lookup at all -- it finds
    # neither the stub NOR reports a conflict, it just silently falls
    # through to whatever real `gcloud` is on the system PATH (verified:
    # this repo's REAL Cloud SDK gcloud is on PATH and would otherwise hang
    # this test on an interactive API-enablement prompt). Ask bash itself
    # for tmp_path's mount-mapped POSIX path (e.g. "/tmp/...") instead of
    # trusting pathlib's own slash-flipping.
    bash_tmp_dir = subprocess.run(
        [bash, "-c", "pwd"], capture_output=True, text=True, cwd=str(tmp_path)
    ).stdout.strip()
    assert bash_tmp_dir, "could not resolve tmp_path to a bash-visible POSIX path"

    driver = tmp_path / "driver.sh"
    driver.write_text(
        f'cd "{REPO_ROOT.as_posix()}"\n'
        f'export PATH="{bash_tmp_dir}:$PATH"\n'
        'export PROJECT_ID="test-project"\n'
        + rendered,
        encoding="utf-8", newline="\n",
    )

    result = subprocess.run(
        [bash, str(driver)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        timeout=60,
    )

    assert result.returncode == 0, (
        f"admin-service-deploy-tagged crashed:\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert marker.exists(), (
        "admin-service-deploy-tagged never reached the (stubbed) "
        f"gcloud run deploy call:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    invoked = marker.read_text(encoding="utf-8")
    assert "ADMIN_SERVICE_URL=https://polyglot-admin-fake.a.run.app" in invoked, (
        f"gcloud run deploy was not passed the live-resolved ADMIN_SERVICE_URL: {invoked!r}"
    )
    assert (
        "BACKEND_URLS_JSON=demo=https://polyglot-backend-fake.a.run.app;"
        "staging=https://polyglot-backend-staging-fake.a.run.app" in invoked
    ), f"gcloud run deploy was not passed the live-resolved BACKEND_URLS_JSON: {invoked!r}"
    assert "FORM_KITS_MODE=gcs" in invoked, (
        f"gcloud run deploy was not passed FORM_KITS_MODE: {invoked!r}"
    )
    assert "FORM_KITS_GCS_BUCKET=test-project-form-kits" in invoked, (
        f"gcloud run deploy was not passed FORM_KITS_GCS_BUCKET: {invoked!r}"
    )
    assert "FORM_KITS_REMOTE_PREFIX=form-kits" in invoked, (
        f"gcloud run deploy was not passed FORM_KITS_REMOTE_PREFIX: {invoked!r}"
    )


# Cloud Build's own built-in substitutions. A bare $NAME is legal in a step
# body ONLY if the name is one of these or is declared under `substitutions:`
# in the file itself; everything else is a bash variable that MUST be written
# $$NAME. Source: Cloud Build "Substituting variable values" reference.
CLOUD_BUILD_BUILTINS = frozenset(
    {
        "PROJECT_ID",
        "PROJECT_NUMBER",
        "BUILD_ID",
        "LOCATION",
        "COMMIT_SHA",
        "SHORT_SHA",
        "REVISION_ID",
        "REPO_NAME",
        "REPO_FULL_NAME",
        "BRANCH_NAME",
        "TAG_NAME",
        "TRIGGER_NAME",
        "TRIGGER_BUILD_CONFIG_PATH",
        "SERVICE_ACCOUNT",
        "SERVICE_ACCOUNT_EMAIL",
    }
)

# $$NAME (escaped, reaches bash) must be consumed before $NAME is matched, or
# the second alternative would see the trailing half of every escaped pair.
_DOLLAR_REF = re.compile(
    r"\$\$\{?[A-Za-z_][A-Za-z0-9_]*"          # escaped: fine, skip
    r"|\$\{?([A-Za-z_][A-Za-z0-9_]*)"          # bare: must be a substitution
)


def _bare_substitution_refs(body: str) -> set[str]:
    """Every $NAME in a step body that Cloud Build will try to substitute."""
    return {m.group(1) for m in _DOLLAR_REF.finditer(body) if m.group(1)}


def test_every_bare_dollar_reference_is_a_real_substitution():
    """A bash variable spelled $NAME is silently blanked before bash runs.

    Cloud Build substitutes over this file BEFORE the step's shell sees it. An
    unmatched $NAME normally errors -- but a TRIGGER-invoked build sets
    ALLOW_LOOSE by default and cannot disable it, and every build here is
    trigger-invoked, so an unmatched reference becomes the EMPTY STRING and the
    build proceeds. `gcloud run deploy "$SERVICE" --set-env-vars="$BACKEND_ENV"`
    would reach gcloud as `gcloud run deploy "" --set-env-vars=""`: the exact
    "config silently emptied" failure the channel files were introduced to
    prevent.

    The legal set is DERIVED -- the built-in list plus whatever the file itself
    declares under `substitutions:` -- so adding a substitution widens it
    automatically while adding a bash variable does not (CLAUDE.md scar #8:
    pin the SET, not the instance).
    """
    spec = yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))
    declared = set(spec.get("substitutions", {}))
    assert declared, "cloudbuild.yaml declares no substitutions -- test is vacuous"
    allowed = CLOUD_BUILD_BUILTINS | declared

    offenders: dict[str, list[str]] = {}
    for step in spec["steps"]:
        body = step["args"][-1]
        bad = sorted(_bare_substitution_refs(body) - allowed)
        if bad:
            offenders[step["id"]] = bad

    assert not offenders, (
        "these step bodies reference $NAME for names Cloud Build cannot "
        "substitute, so each is replaced with the EMPTY STRING before bash "
        "runs -- write them $$NAME:\n"
        + "\n".join(f"  {sid}: {names}" for sid, names in offenders.items())
    )


def test_the_backend_deploy_step_escapes_its_shell_variables():
    """The specific names finding 1 found blanked, pinned by name.

    The derived test above is the general guard; this one fails with a direct
    message if the backend deploy step specifically regresses, because that
    step is the one whose blanking produced a live `gcloud run deploy ""`.
    """
    spec = yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))
    steps = {s["id"]: s["args"][-1] for s in spec["steps"]}

    for name in ("SERVICE", "BACKEND_ENV", "CHANNEL_ENV", "CHANNEL_FILE",
                 "CHANNEL_SA", "CHANNEL_SECRETS", "SA_FLAG", "SECRETS_FLAG"):
        body = steps["backend-deploy"]
        assert f"$${name}" in body or f"$${{{name}" in body, (
            f"backend-deploy no longer escapes ${name} as $${name}"
        )
        assert not re.search(rf"(?<!\$)\${{?{name}\b", body), (
            f"backend-deploy has a BARE ${name} -- Cloud Build blanks it"
        )

    assert not re.search(r"(?<!\$)\$\{?SERVICE\b", steps["backend-reachability-gate"]), (
        "the reachability gate has a bare $SERVICE; blanked, it calls "
        "verify_service_publicly_reachable \"\", whose IAM read then fails and "
        "is treated as INCONCLUSIVE -- it warns and returns 0, turning bd "
        "polyglot-pdf-pidtg's gate into a no-op"
    )


# The node apps the verify target gates. schema-editor has a CI job too but no
# cloudbuild verify step (it is not part of the deploy set this build file
# serves), so the mapping is explicit rather than "every ci.yml node job".
VERIFIED_NODE_APPS = {
    "verify-frontend": "frontend",
    "verify-admin-console": "admin-console",
}


def _ci_commands_for(app: str) -> list[str]:
    """The npm commands ci.yml runs for one app, read from ci.yml itself.

    Derived, not transcribed: when CI adds a step for an app, this widens and
    the parity assertion below starts requiring it here too.
    """
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    spec = yaml.safe_load(ci)
    found: list[str] = []
    for job in spec["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run", "")
            wd = step.get("working-directory", "")
            # A step CI itself does not fail on (the informational security
            # scans, continue-on-error) is not part of "CI's green" and so
            # not something the verify target must reproduce.
            if step.get("continue-on-error") is True:
                continue
            if wd == app and run.startswith("npm"):
                found.append(run.strip())
    return found


@pytest.mark.parametrize("step_id,app", sorted(VERIFIED_NODE_APPS.items()))
def test_the_verify_target_runs_the_same_npm_commands_as_ci(by_id, step_id, app):
    """build_checks/{_SHA} means "this commit's suites passed" -- as CI judges it.

    Two ways this step can mean LESS than CI's green, both of which it did:

      1. `npm test` instead of `npm run test:run`. `test` maps to bare
         `vitest`, whose watch mode resolves to `!isCI && process.stdin.isTTY`.
         A build step has no TTY so it does not hang today, but that is the
         runner's accident, not the command's contract -- and a hung verify
         blocks every deploy for that SHA until the 3600s timeout.
      2. No `npm run typecheck`. vitest is transpile-only, so a commit failing
         `tsc --noEmit` still earned a success record -- the exact regression
         bd polyglot-pdf-1rgr and bd polyglot-pdf-b6943 added those CI steps
         for.

    The expectation is DERIVED from ci.yml, so the two cannot drift silently in
    either direction (CLAUDE.md scar #8).
    """
    body = script_of(by_id[step_id])
    expected = _ci_commands_for(app)
    assert expected, f"ci.yml declares no npm steps for {app} -- test is vacuous"

    for command in expected:
        assert command in body, (
            f"ci.yml runs `{command}` for {app}, but cloudbuild.yaml's "
            f"{step_id} step does not -- the build_checks record would vouch "
            f"for a commit CI would reject"
        )

    # `npm test` is the watch-mode sibling; its presence means the step is
    # running something other than the command CI runs. Scan the COMMAND
    # lines only -- the step's own comment explains why `npm test` is
    # wrong, and a whole-body search would match that prose and fail on an
    # already-correct file.
    command_lines = [
        line for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    offenders = [l for l in command_lines if re.search(r"npm test\b", l)]
    assert not offenders, (
        f"{step_id} runs watch-mode `npm test`; ci.yml runs "
        f"`npm run test:run`. Offending line(s): {offenders}"
    )


# Images that ship PEP 668's EXTERNALLY-MANAGED marker, under which a bare
# `pip install` into the system interpreter exits non-zero. cloud-sdk is
# Debian-based; Debian has shipped the marker since bookworm (12).
PEP_668_IMAGES = ("cloudsdktool/cloud-sdk",)


def test_no_step_pip_installs_into_an_externally_managed_interpreter():
    """A bare `pip install` on a Debian-based image is refused by PEP 668.

    `error: externally-managed-environment` exits non-zero, and every step here
    runs under `set -euo pipefail`, so the step fails. That matters most for
    gate-build-checks, which is the FIRST step of every deploy target: if it
    cannot install its client the gate never reads build_checks at all.

    The fix is the image, not a flag -- these steps need pip and
    google-cloud-firestore but no gcloud, so an official python image is both
    safer and smaller. `--break-system-packages` would paper over it.

    Pinned as a PROPERTY of the whole file (no step may combine the two)
    rather than as the current image of two named steps, so a new pip-using
    step on a cloud-sdk image fails here too (CLAUDE.md scar #8).
    """
    spec = yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))

    offenders = [
        step["id"]
        for step in spec["steps"]
        if "pip install" in step["args"][-1]
        and any(image in step["name"] for image in PEP_668_IMAGES)
    ]

    assert not offenders, (
        "these steps run `pip install` on a Debian-based image whose PEP 668 "
        "EXTERNALLY-MANAGED marker refuses it, failing the step under "
        f"set -e: {offenders}. Use python:3.12 -- they need no gcloud."
    )


def test_no_step_runs_npx_or_npm_on_a_non_node_image():
    """`npx`/`npm` need Node; gcr.io/google.com/cloudsdktool/cloud-sdk:slim
    (gcloud + Debian + Python only, no Node) does not have it -- a step that
    calls either on that image fails outright with "command not found"
    under set -e (review round: bd polyglot-pdf-ywxoh: firestore-rules-
    deploy shipped on cloud-sdk:slim calling `npx firebase-tools`, and no
    test executed the step to catch it).

    Pinned as a PROPERTY of the whole file (no step may combine `npx`/`npm`
    with a non-node image), not as a fact about firestore-rules-deploy by
    name, so a future step that adds an npx/npm call on the wrong image
    fails here too (CLAUDE.md scar #8) -- mirroring
    test_no_step_pip_installs_into_an_externally_managed_interpreter's shape
    for the analogous node/gcloud image split.
    """
    spec = yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))

    offenders = [
        step["id"]
        for step in spec["steps"]
        if re.search(r"(?:^|[\s\"'`|;&(])(?:npx|npm)\b", step["args"][-1])
        and not step["name"].startswith("node:")
    ]

    assert not offenders, (
        "these steps call npx/npm but do not run on a node: image, so the "
        f"call fails with 'command not found' under set -e: {offenders}. "
        "Move the step to node:22 (matching every other npx/npm step here), "
        "or split the npx/npm call into its own node:22 step if the "
        "remainder of the step genuinely needs gcloud/docker."
    )


def test_the_build_check_steps_can_import_their_firestore_client():
    """The two gate steps must be on an image where their pip install works.

    The property test above forbids the broken combination; this one states
    the positive requirement, so deleting the pip line (which would also
    satisfy the property test) still fails: the steps genuinely need the
    client, because record_build_check.py imports google.cloud.firestore.
    """
    spec = yaml.safe_load(CLOUDBUILD.read_text(encoding="utf-8"))
    by_step = {step["id"]: step for step in spec["steps"]}

    for step_id in ("gate-build-checks", "record-build-check"):
        step = by_step[step_id]
        body = step["args"][-1]
        assert "google-cloud-firestore" in body, (
            f"{step_id} does not install google-cloud-firestore, but "
            "record_build_check.py imports google.cloud.firestore"
        )
        assert step["name"].startswith("python:"), (
            f"{step_id} must run on an official python image (no PEP 668 "
            f"marker); it is on {step['name']}"
        )


# ---------------------------------------------------------------------------
# bd polyglot-pdf-ywxoh (Epic 4 bead 4.2) -- the remaining targets and the
# in-build gates. Exit criterion 1: every deploy target's first REAL step is
# the build_checks gate, the demo-side targets carry the staging-success
# gate, each staging target's last step records a deployment row, and every
# site target carries the connected-source assertion.
# ---------------------------------------------------------------------------

# Every target 4.2 implements (verify and backend-* are 4.1's -- see
# IMPLEMENTED_TARGETS above). "landing" is deliberately absent: the plan
# leaves it a maintainer call, and it stays a named-but-failing step.
YWXOH_DEPLOY_TARGETS = (
    "backend-staging",
    "backend-demo",
    "frontend-staging",
    "frontend-demo",
    "editor",
    "form-kits",
    "firestore-rules",
    "admin-service",
    "admin-console-candidate",
    "admin-console",
)


@pytest.mark.parametrize("target", YWXOH_DEPLOY_TARGETS)
def test_every_ywxoh_target_is_in_the_implemented_pass_through_arm(by_id, target):
    """The inverse of test_every_unimplemented_target_fails_loudly: a REAL
    target must not be silently absent from unimplemented-targets' implemented
    case arm, which would hard-abort a legitimately implemented target in
    production ("ABORT: unknown target") with zero test signal.

    test_every_unimplemented_target_fails_loudly only ever checked the OLD
    3-target IMPLEMENTED_TARGETS list (bead 4.1's verify/backend-staging/
    backend-demo) against this arm -- none of this bead's 8 new targets were
    pinned here, so a target silently dropped into the catch-all `*) ABORT`
    branch would have passed that test untouched. This test is keyed off
    YWXOH_DEPLOY_TARGETS (independently maintained, not derived from the yaml
    body the way test_the_trigger_script_names_a_trigger_for_every_target is)
    so it actually catches that regression.

    Mutation-verified: removing "editor" from the implemented case-arm's
    pattern list at cloudbuild.yaml's unimplemented-targets step (so `editor`
    falls through to the `*) ABORT: unknown target` branch) turns this red
    for target="editor" without affecting the other 9 targets.
    """
    body = script_of(by_id["unimplemented-targets"])
    lines = [line.strip() for line in body.splitlines()]
    implemented_idx = next(
        i for i, line in enumerate(lines) if line.startswith("case ")
    )
    not_implemented_idx = lines.index('echo "target not implemented"')
    implemented_arm = "\n".join(lines[implemented_idx:not_implemented_idx])
    target_pattern = re.compile(r'(?<![\w-])' + re.escape(target) + r'(?![\w-])')
    assert target_pattern.search(implemented_arm), (
        f"{target} is a real ywxoh (bead 4.2) target but does not appear in "
        "unimplemented-targets' implemented pass-through arm -- a build for "
        f"{target} would fall through to the ABORT: unknown target branch "
        "and hard-fail in production"
    )


# The demo-side targets the plan singles out: "backend-demo, frontend-demo
# and admin-service traffic shift additionally require a deployments
# record". admin-service's OWN target implements both halves (deploy the
# tagged candidate, then shift traffic) as one _TARGET value, so it is
# included once here and its gate step is identified by name below rather
# than by target name.
STAGING_GATED_DEMO_TARGETS = ("backend-demo", "frontend-demo")

# Every STAGING target that must write its own success row (plan: "each
# staging target's LAST step writes its own success row to deployments").
# admin-service is its OWN staging tier (tagged-candidate-then-shift), so its
# record step fires unconditionally for that target rather than being
# staging-channel-gated the way backend/frontend are. UNLIKE backend/frontend,
# admin-service's record step does NOT run last -- it runs before its own
# admin-service-staging-gate (which reads the very row it writes, in the same
# build) and before admin-service-shift-traffic. See
# test_each_staging_target_records_its_own_success_row's docstring.
STAGING_RECORDING_TARGETS = ("backend-staging", "frontend-staging", "admin-service")

# Every SITE target: builds a frontend bundle from a directory .gcloudignore
# excludes from a tarball build, so each must refuse an empty COMMIT_SHA.
SITE_TARGETS = (
    "frontend-staging",
    "frontend-demo",
    "editor",
    "admin-console-candidate",
    "admin-console",
)


def _mutating_step_ids_for_target(steps, target: str) -> list[str]:
    """Every step whose body actually DOES something for `target` -- i.e. it
    is not merely present but its skip-guard would let it proceed for this
    target. A step is included if the target literal (or its channel-derived
    prefix, e.g. "backend-*") appears in a `case`/`if` guard alongside the
    step's own mutating verb, which is a conservative enough signal for this
    file's purpose: proving ORDER relative to the gates, not enumerating
    every side effect.
    """
    hits = []
    for step in steps:
        body = script_of(step)
        # A step whose guard would SKIP this target contributes nothing.
        if f'"{target}"' not in body and target.split("-")[0] + "-*" not in body:
            continue
        if "skip (target" not in body and "${_TARGET}" not in body:
            continue
        hits.append(step["id"])
    return hits


@pytest.mark.parametrize("target", YWXOH_DEPLOY_TARGETS)
def test_every_ywxoh_deploy_target_is_gated_by_build_checks(by_id, steps, target):
    """Exit criterion 1, clause 1: every deploy target's FIRST step is the
    build_checks gate.

    "First step" here means POSITIONALLY before any step that does real work
    for this target -- the gate-build-checks step itself is target-agnostic
    (it runs for every target except verify), so the property to prove is
    that no step touching `target` runs BEFORE it, mirroring
    test_the_build_checks_gate_precedes_every_deploy_step's method but keyed
    per target rather than globally.

    Mutation-verified: moving any one of this bead's steps above
    gate-build-checks (as staging-verified-gate itself was, before the
    ordering fix during development) turns this red for that target.
    """
    order = {step["id"]: i for i, step in enumerate(steps)}
    gate = order["gate-build-checks"]
    # A whole-word match: the target name bounded by non-identifier
    # characters on both sides, so it matches EITHER a quoted literal
    # ("backend-staging") or a bare case-arm pattern (admin-console-candidate|
    # admin-console) ;;) without matching a longer name that merely CONTAINS
    # this one as a substring (e.g. "admin-console" must not match inside
    # "admin-console-candidate").
    target_pattern = re.compile(
        r'(?<![\w-])' + re.escape(target) + r'(?![\w-])'
    )
    for step in steps:
        if step["id"] in (
            "gate-build-checks",
            "require-sha",
            # A DELIBERATE pre-gate step: cheap and structural (an empty
            # COMMIT_SHA check), placed BEFORE gate-build-checks on purpose
            # so a tarball-sourced site build fails fast without waiting on
            # the (possibly expensive, possibly inconclusive) build_checks
            # read. It names every site target in its case statement but is
            # not "real work" in the sense this test guards -- it deploys
            # nothing and mutates nothing.
            "require-connected-source-for-site-targets",
        ):
            continue
        body = script_of(step)
        # A step that explicitly checks THIS target (by literal, by bare
        # case-arm name, or by channel-suffix wildcard) and does not
        # universally skip is presumed to run for it.
        runs_for_target = (
            target_pattern.search(body) is not None
            or (target.endswith("-staging") and 'in backend-*' in body and target.startswith("backend"))
            or (target.endswith("-demo") and 'in backend-*' in body and target.startswith("backend"))
            or (target.endswith("-staging") and 'in frontend-*' in body and target.startswith("frontend"))
            or (target.endswith("-demo") and 'in frontend-*' in body and target.startswith("frontend"))
        )
        if not runs_for_target:
            continue
        assert order[step["id"]] > gate, (
            f"step {step['id']!r} appears to run for target {target!r} at "
            f"index {order[step['id']]}, before the build_checks gate at "
            f"index {gate}. A commit whose suites failed would still reach "
            f"this step for {target}."
        )


@pytest.mark.parametrize("target", STAGING_GATED_DEMO_TARGETS)
def test_demo_side_targets_carry_the_staging_success_gate(by_id, steps, target):
    """Exit criterion 1, clause 2: the three demo-side targets carry the
    staging-success gate (plan: 'backend-demo, frontend-demo and
    admin-service traffic shift additionally require a deployments record').

    Mutation-verified: renaming staging-verified-gate's case arm away from
    `backend-demo|frontend-demo` (e.g. to just `backend-demo`) makes this red
    for frontend-demo -- confirmed by hand during development.
    """
    body = script_of(by_id["staging-verified-gate"])
    assert target in body, (
        f"staging-verified-gate's case statement does not mention {target!r}, "
        f"so a demo build for it would proceed without checking staging"
    )
    assert "promotion_gate.py" in body, (
        "staging-verified-gate does not call scripts/promotion_gate.py"
    )

    order = {step["id"]: i for i, step in enumerate(steps)}
    gate_idx = order["staging-verified-gate"]
    # The target's OWN deploy step(s) must come after the gate.
    family = target.rsplit("-", 1)[0]
    deploy_step = "{}-deploy".format(family) if family == "backend" else "{}-build-deploy".format(family)
    assert deploy_step in order, f"could not find the deploy step for {target}"
    assert order[deploy_step] > gate_idx, (
        f"{deploy_step} (index {order[deploy_step]}) runs before "
        f"staging-verified-gate (index {gate_idx}) -- a demo deploy for "
        f"{target} could ship before the staging check runs"
    )


@pytest.mark.parametrize("target", STAGING_GATED_DEMO_TARGETS)
def test_staging_verified_gate_actually_evaluates_at_runtime(by_id, target, tmp_path):
    """Exit criterion 1, clause 2, RUNTIME half.

    test_demo_side_targets_carry_the_staging_success_gate (above) only
    substring-matches the case statement; it cannot tell a live case arm from
    one that crashes before it is ever reached. This test actually RUNS
    staging-verified-gate's script with Cloud Build's substitution pass
    simulated textually (the same replacement Cloud Build performs on
    "${_TARGET}" et al. before handing the script to bash) and a stub
    `python`/`pip` on PATH standing in for the real interpreter, then
    asserts the stub was actually invoked with the right --target-family.

    Regression guard for a real incident: "$${_TARGET%-demo}" (a $$-escaped
    suffix-strip applied directly to the substitution token, rather than to a
    bash variable holding its value) parses fine, passes
    test_every_step_script_is_valid_bash (syntax only), and substring-matches
    the assertions above -- but crashes EVERY backend-demo/frontend-demo
    build with "_TARGET: unbound variable" under this file's set -euo
    pipefail, because Cloud Build substitutions are not bash variables and $$
    defers the expression to bash verbatim. Reverting the TGT="${_TARGET}"
    assignment and taking "$${TGT%-demo}" directly on "${_TARGET}" instead
    reproduces exactly that crash (confirmed by hand during the ywxoh review
    round that found this).
    """
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover
        pytest.skip("bash not on PATH")

    script = script_of(by_id["staging-verified-gate"])
    # Simulate Cloud Build's OWN substitution pass: "${_TARGET}" and
    # "${_SHA}" are replaced textually before bash ever sees the script;
    # only $$-escaped tokens are left for bash. Real Cloud Build would
    # reject an empty _SHA well before this step (require-sha runs first),
    # so a nonempty placeholder is the realistic case.
    # Cloud Build ALSO collapses every "$$" to a literal "$" before bash
    # ever sees the script (that is what "$$" escaping means) -- do that
    # LAST so it never touches the "${_TARGET}"/"${_SHA}" substitution
    # braces themselves.
    rendered = (
        script.replace("${_TARGET}", target)
        .replace("${_SHA}", "deadbeef")
        .replace("$$", "$")
    )

    marker = tmp_path / "invoked_with.txt"
    # Extensionless shell-script stubs, chmod +x, PATH-prepended with bash's
    # OWN idea of the directory (tmp_path.as_posix()) -- a Windows-style
    # "C:/..." PATH entry is not resolved the same way inside Git Bash, and a
    # .bat/.exe stub is not found via `command -v python` at all (mirrors
    # tests/test_deploy_reachability_gate.py's _run_wrapper).
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/bash\n"
        f'echo "$@" > "{marker.as_posix()}"\n'
        "exit 0\n",
        encoding="utf-8", newline="\n",
    )
    fake_python.chmod(0o755)
    fake_pip = tmp_path / "pip"
    fake_pip.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8", newline="\n")
    fake_pip.chmod(0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        f'cd "{tmp_path.as_posix()}"\n'
        'export PATH="$PWD:$PATH"\n'
        'export PROJECT_ID="test-project"\n'
        + rendered,
        encoding="utf-8", newline="\n",
    )

    result = subprocess.run(
        [bash, str(driver)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        timeout=60,
    )

    assert result.returncode == 0, (
        f"staging-verified-gate crashed for target {target!r} instead of "
        f"reaching promotion_gate.py:\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert marker.exists(), (
        f"staging-verified-gate for target {target!r} exited 0 without ever "
        f"invoking the (stubbed) python interpreter -- it likely hit the "
        f"'*) skip' arm instead of the intended case"
    )
    invoked = marker.read_text(encoding="utf-8")
    expected_family = target.rsplit("-", 1)[0]
    assert f"--target-family {expected_family}" in invoked, (
        f"staging-verified-gate invoked python with {invoked!r}, which does "
        f"not contain the expected '--target-family {expected_family}'"
    )

    # bd polyglot-pdf-jub5f (4.4) exit criterion 2: the gate step must pass
    # BOTH the target-derived family (asserted above) AND the SHA it is
    # gating -- checking family alone would let ANY sha for the right
    # family through the shell invocation; only passing the real _SHA lets
    # staging_verified()'s own exact-sha comparison run against the right
    # commit at all.
    assert "--sha deadbeef" in invoked, (
        f"staging-verified-gate invoked python with {invoked!r}, which does "
        f"not contain the expected '--sha deadbeef' (the rendered _SHA)"
    )


def test_admin_service_traffic_shift_carries_the_staging_gate(by_id, steps):
    """The third demo-side case: admin-service's TRAFFIC SHIFT specifically
    (not its tagged-candidate deploy, which is its own staging tier)."""
    body = script_of(by_id["admin-service-staging-gate"])
    assert "admin-service" in body
    assert "promotion_gate.py" in body

    order = {step["id"]: i for i, step in enumerate(steps)}
    assert order["admin-service-shift-traffic"] > order["admin-service-staging-gate"], (
        "admin-service-shift-traffic runs before admin-service-staging-gate -- "
        "traffic could shift before the staging check runs"
    )
    # admin-service has no separate staging build -- its OWN
    # record-deployment step must satisfy its OWN gate, in the same build,
    # so the record step has to run FIRST. (Bootstrap-deadlock regression
    # guard: this was reversed until the ywxoh fresh-eyes review caught that
    # no build could ever satisfy a gate checked before anything wrote the
    # row it looks for.)
    assert order["admin-service-record-deployment"] < order["admin-service-staging-gate"], (
        "admin-service-record-deployment runs AFTER admin-service-staging-gate -- "
        "the gate can never find a row, since nothing wrote one yet in this build "
        "(a bootstrap deadlock: admin-service deploys would fail every time)"
    )


def test_admin_service_staging_gate_actually_evaluates_at_runtime(by_id, tmp_path):
    """bd polyglot-pdf-jub5f (4.4) exit criterion 2, admin-service's RUNTIME
    half -- the sibling of test_staging_verified_gate_actually_evaluates_
    at_runtime above, which only covers backend-demo/frontend-demo.
    admin-service-staging-gate is a SEPARATE step with its own case
    statement (a bare "${_TARGET}" != "admin-service" check, not the
    TGT-variable pattern staging-verified-gate uses), so the same class of
    substitution/escaping bug could hide here independently -- a static
    substring match (test_admin_service_traffic_shift_carries_the_staging_
    gate, above) cannot tell a live case arm from one that never reaches
    promotion_gate.py at all.
    """
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover
        pytest.skip("bash not on PATH")

    script = script_of(by_id["admin-service-staging-gate"])
    rendered = (
        script.replace("${_TARGET}", "admin-service")
        .replace("${_SHA}", "deadbeef")
        .replace("$$", "$")
    )

    marker = tmp_path / "invoked_with.txt"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/bash\n"
        f'echo "$@" > "{marker.as_posix()}"\n'
        "exit 0\n",
        encoding="utf-8", newline="\n",
    )
    fake_python.chmod(0o755)
    fake_pip = tmp_path / "pip"
    fake_pip.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8", newline="\n")
    fake_pip.chmod(0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        f'cd "{tmp_path.as_posix()}"\n'
        'export PATH="$PWD:$PATH"\n'
        'export PROJECT_ID="test-project"\n'
        + rendered,
        encoding="utf-8", newline="\n",
    )

    result = subprocess.run(
        [bash, str(driver)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        timeout=60,
    )

    assert result.returncode == 0, (
        f"admin-service-staging-gate crashed instead of reaching "
        f"promotion_gate.py:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert marker.exists(), (
        "admin-service-staging-gate exited 0 without ever invoking the "
        "(stubbed) python interpreter -- it likely hit the '*) skip' arm"
    )
    invoked = marker.read_text(encoding="utf-8")
    assert "--target-family admin-service" in invoked, (
        f"admin-service-staging-gate invoked python with {invoked!r}, which "
        f"does not contain '--target-family admin-service'"
    )
    assert "--sha deadbeef" in invoked, (
        f"admin-service-staging-gate invoked python with {invoked!r}, which "
        f"does not contain the expected '--sha deadbeef' (the rendered _SHA)"
    )


@pytest.mark.parametrize("target", STAGING_RECORDING_TARGETS)
def test_each_staging_target_records_its_own_success_row(by_id, steps, target):
    """Exit criterion 1, clause 3: each staging target writes its own
    deployments row (plan: avoids racing bead 4.3's Pub/Sub webhook, and
    covers bash-triggered builds the webhook alone would still need this for).

    "LAST step" (the plan's literal phrasing) holds for backend-staging and
    frontend-staging, which record AFTER their own deploy in a build no
    later step depends on reading. admin-service is the deliberate
    exception: it has no separate staging build, so its OWN
    admin-service-staging-gate has to read a row THIS SAME build wrote --
    which means admin-service-record-deployment must run BEFORE the gate
    (and therefore before the traffic shift too), not last. See that step's
    comment in cloudbuild.yaml for the bootstrap-deadlock this avoids.

    Every target's record step is also pinned to the LITERAL channel value
    "staging" (not just "some --channel flag exists") -- the exact gap a
    prior review round found: admin-service's trigger fixes _CHANNEL to
    "admin" (scripts/setup-cloud-build.sh), so a step written as
    `--channel "${_CHANNEL}"` would silently record "admin" and the staging
    gate could never be satisfied. Asserting the flag's PRESENCE alone does
    not catch that -- only the literal value does.

    Mutation-verified: deleting the record_deployment.py call from any one of
    the three record steps (confirmed on frontend-record-deployment during
    development) makes this red for that target without affecting the other
    two -- proving the check is per-target, not a single global grep.
    Separately mutation-verified: reverting `--channel staging` back to
    `--channel "${_CHANNEL}"` on admin-service-record-deployment makes the
    literal-value assertion below red without touching the two siblings.
    """
    record_step_by_target = {
        "backend-staging": "backend-record-deployment",
        "frontend-staging": "frontend-record-deployment",
        "admin-service": "admin-service-record-deployment",
    }
    step_id = record_step_by_target[target]
    assert step_id in by_id, f"no {step_id} step in cloudbuild.yaml"
    body = script_of(by_id[step_id])
    assert "python scripts/record_deployment.py" in body
    assert "--channel" in body
    assert "--status success" in body
    assert "--build-id" in body and "$BUILD_ID" in body
    # The literal value, not just the flag's presence -- see docstring.
    assert re.search(r'--channel\s+staging(\s|$)', body), (
        f"{step_id} does not record the LITERAL channel value \"staging\" "
        f"(found: {body!r}) -- a demo/traffic-shift gate reading for "
        f"channel==\"staging\" would never find this row"
    )

    order = {step["id"]: i for i, step in enumerate(steps)}
    if target == "admin-service":
        # The deliberate exception: record BEFORE the gate it satisfies (and
        # therefore before the traffic shift), not last. Pinned in detail by
        # test_admin_service_traffic_shift_carries_the_staging_gate above;
        # here just confirm it precedes its own deploy-tagged/verify-tagged
        # predecessors' natural successor, i.e. it isn't sitting somewhere
        # nonsensical like before the tagged deploy even happens.
        assert order[step_id] > order["admin-service-verify-tagged"], (
            f"{step_id} runs before admin-service-verify-tagged -- it would "
            "record success for a candidate that was never health-checked"
        )
        assert order[step_id] < order["admin-service-shift-traffic"], (
            f"{step_id} runs after admin-service-shift-traffic -- traffic "
            "would have already moved before this build's own success row "
            "was durable"
        )
        return

    # "LAST step" -- no other step for this target's family runs after it,
    # among the steps THIS bead added for that family.
    family_steps = {
        "backend-staging": ["backend-build-image", "backend-deploy",
                             "backend-reachability-gate",
                             "backend-record-deployment"],
        "frontend-staging": ["frontend-resolve-urls", "frontend-build-deploy",
                              "frontend-record-deployment"],
    }[target]
    indices = [order[s] for s in family_steps]
    assert order[step_id] == max(indices), (
        f"{step_id} is not the LAST step among {family_steps} for {target}"
    )


@pytest.mark.parametrize("target", SITE_TARGETS)
def test_every_site_target_requires_a_connected_source(by_id, steps, target):
    """Exit criterion 1, clause 4: every site target asserts COMMIT_SHA is
    non-empty (a tarball build cannot see the site directories at all, since
    .gcloudignore excludes them -- see that file's own comment).

    Mutation-verified: narrowing require-connected-source-for-site-targets's
    case arm to omit one target name (confirmed on admin-console-candidate
    during development) makes this red for exactly that target.
    """
    body = script_of(by_id["require-connected-source-for-site-targets"])
    assert target in body, (
        f"require-connected-source-for-site-targets does not mention "
        f"{target!r}, so that site target could build from a tarball"
    )
    assert "COMMIT_SHA" in body and "ABORT" in body

    order = {step["id"]: i for i, step in enumerate(steps)}
    gate_idx = order["require-connected-source-for-site-targets"]
    build_step_by_target = {
        "frontend-staging": "frontend-build-deploy",
        "frontend-demo": "frontend-build-deploy",
        "editor": "editor-build-deploy",
        "admin-console-candidate": "admin-console-build-deploy",
        "admin-console": "admin-console-build-deploy",
    }
    build_step = build_step_by_target[target]
    assert order[build_step] > gate_idx, (
        f"{build_step} (index {order[build_step]}) runs before the "
        f"connected-source check (index {gate_idx})"
    )


def test_form_kits_requires_a_connected_source(by_id, steps):
    """(Not in the original handoff, caught by cross-surface review of bd
    polyglot-pdf-ywxoh.) form-kits is NOT a "site" target -- it deploys no
    Hosting site -- but shares the exact failure mode SITE_TARGETS are
    guarded against: .gcloudignore excludes form-kits/ from a tarball
    build's source, and scripts/write_kits_manifest.py silently emits a
    valid, EMPTY manifest (forms: []) when the directory it is pointed at
    does not exist, exiting 0. Without this gate, a tarball-sourced
    `form-kits` build would overwrite the demo's live form list with zero
    forms on an apparently clean build.

    Mutation-verified: removing "form-kits" from
    require-connected-source-for-site-targets's case arm (confirmed by hand
    during the ywxoh review round that found this) makes this red.
    """
    body = script_of(by_id["require-connected-source-for-site-targets"])
    # A whole-word, CASE-ARM-anchored match: "form-kits" as a bare case
    # pattern (bounded by "|"/")" on either side), not merely a substring
    # of an explanatory comment or echo string elsewhere in the same
    # step -- a prose mention would satisfy a plain "in body" check
    # while the case arm itself still omitted the target entirely.
    assert re.search(r'(?<![\w-])form-kits(?![\w-])[|)]', body), (
        "require-connected-source-for-site-targets's CASE ARM does not "
        "list form-kits (a mention elsewhere in the step, e.g. a comment, "
        "does not count) -- a tarball build for that target could "
        "proceed against a form-kits/ directory it cannot actually see"
    )
    assert "COMMIT_SHA" in body and "ABORT" in body

    order = {step["id"]: i for i, step in enumerate(steps)}
    gate_idx = order["require-connected-source-for-site-targets"]
    for step_id in ("form-kits-upload", "form-kits-manifest"):
        assert order[step_id] > gate_idx, (
            f"{step_id} (index {order[step_id]}) runs before the "
            f"connected-source check (index {gate_idx})"
        )


def test_gcloudignore_excludes_admin_console():
    """The premise of the connected-source gate: admin-console/ must
    actually be excluded from a tarball build, or the gate is protecting
    against a scenario that cannot occur."""
    ignore = (REPO_ROOT / ".gcloudignore").read_text(encoding="utf-8")
    lines = [l.strip() for l in ignore.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert "admin-console/" in lines, (
        ".gcloudignore does not exclude admin-console/ -- a tarball build "
        "could then see and build it, defeating the connected-source gate's "
        "whole premise"
    )


def test_promotion_gate_module_and_cli_agree_on_the_predicate():
    """scripts/promotion_gate.py must call the SAME predicate the future
    admin route (bead 4.4) will use, not a second copy of the rule."""
    cli = (REPO_ROOT / "scripts" / "promotion_gate.py").read_text(encoding="utf-8")
    assert "from admin_backend.services.promotion_gate import staging_verified" in cli, (
        "scripts/promotion_gate.py does not import the pure predicate from "
        "admin_backend.services.promotion_gate -- it may be reimplementing "
        "the rule instead of sharing it with the future admin route"
    )


def test_promotion_gate_cli_actually_imports_under_its_real_invocation():
    """A substring match on the import line (the test above) cannot catch a
    broken sys.path: cloudbuild.yaml's staging-verified-gate and
    admin-service-staging-gate steps both invoke this as
    `python scripts/promotion_gate.py` from /workspace (the build's
    repo-root checkout) -- NOT as `python -m scripts.promotion_gate` and NOT
    from inside scripts/. That invocation form puts scripts/ (this file's
    own directory), not the repo root, on sys.path[0], so a plain
    `from admin_backend... import ...` at module scope raises
    ModuleNotFoundError before argparse even runs (review round: bd
    polyglot-pdf-ywxoh -- every prior test here stubbed out the `python`
    binary entirely and so never caught this). Actually spawn the real
    interpreter, cwd'd at the repo root exactly as Cloud Build does, and
    assert it reaches argument parsing (a `--target-family`/`--sha` usage or
    argparse error is fine; a traceback naming ModuleNotFoundError is not).

    PYTHONPATH is explicitly stripped from the child's environment: this
    repo's own test-running convention (PYTHONPATH=<worktree> for pytest)
    would otherwise put the repo root on sys.path FOR us and hide exactly
    the bug this test exists to catch (mutation-verified: with the
    subprocess inheriting the parent's PYTHONPATH, this test stayed green
    against the pre-fix module -- Cloud Build's own container carries no
    such variable, so inheriting it here would test a scenario that cannot
    happen in production).
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "scripts/promotion_gate.py", "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert "ModuleNotFoundError" not in result.stderr, (
        "scripts/promotion_gate.py could not import admin_backend when run "
        "the way cloudbuild.yaml actually invokes it (python "
        "scripts/promotion_gate.py from the repo root) -- sys.path[0] is "
        "the script's own scripts/ directory in this invocation form, not "
        f"the repo root:\n{result.stderr}"
    )
    assert result.returncode == 0, (
        f"scripts/promotion_gate.py --help exited {result.returncode} "
        f"instead of printing help:\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


def test_record_deployment_module_exists_and_derives_target_family():
    """scripts/record_deployment.py's target_family() is what lets
    staging_verified() match a staging target's family against a demo
    target's family."""
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import record_deployment  # noqa: E402

    assert record_deployment.target_family("backend-staging") == "backend"
    assert record_deployment.target_family("backend-demo") == "backend"
    assert record_deployment.target_family("frontend-staging") == "frontend"
    assert record_deployment.target_family("admin-service") == "admin-service"


def test_target_family_matches_record_deployment_helper():
    """deploy/targets.py::target_family() is a deliberate INDEPENDENT copy
    of scripts/record_deployment.py::target_family() (bd polyglot-pdf-tb3kp
    -- see deploy/targets.py's own module docstring for why the two are not
    a shared import: one is a build-time script, the other a route-time
    constant module). This test is the drift guard that docstring names --
    it asserts the two never disagree, for every TARGETS entry, so a future
    edit to either copy's suffix list or special-casing fails HERE instead
    of silently diverging (CLAUDE.md scar #8: enumerate the set, then pin
    the set)."""
    import sys as _sys

    _sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import record_deployment  # noqa: E402

    from deploy.targets import TARGETS, target_family

    for target in TARGETS:
        assert target_family(target) == record_deployment.target_family(
            target
        ), (
            "deploy/targets.py::target_family({0!r}) == {1!r} but "
            "scripts/record_deployment.py::target_family({0!r}) == {2!r} "
            "-- the two independent copies have diverged".format(
                target,
                target_family(target),
                record_deployment.target_family(target),
            )
        )


def test_frontend_build_exports_vite_app_channel(by_id):
    """(Not in the original handoff, caught by cross-surface review of bd
    polyglot-pdf-ywxoh.) frontend/src/shared/config.ts::getAppChannel()
    reads VITE_APP_CHANNEL and falls back to 'demo' when it is unset --
    deploy-staging.sh and deploy-demo.sh both export it explicitly for
    exactly that reason (bd polyglot-pdf-z4ljj), because both channels build
    the identical Vite mode (build:schema:demo) and import.meta.env.MODE
    cannot tell them apart. Without this, a Cloud Build frontend-staging
    build would silently claim to be the demo channel on every firm-scoped
    admin-service call, reading and writing the DEMO's Firestore data from
    the staging site.
    """
    body = script_of(by_id["frontend-build-deploy"])
    assert 'export VITE_APP_CHANNEL="${_CHANNEL}"' in body, (
        "frontend-build-deploy does not export VITE_APP_CHANNEL from "
        "${_CHANNEL} -- a staging build would default to the 'demo' "
        "channel and touch the wrong Firestore data"
    )
    # Must run before the actual build command, not after.
    build_idx = body.index("npm run build:schema:demo")
    channel_idx = body.index('export VITE_APP_CHANNEL="${_CHANNEL}"')
    assert channel_idx < build_idx, (
        "VITE_APP_CHANNEL is exported AFTER the build runs, so it would "
        "never reach the bundle"
    )


def test_frontend_resolve_urls_aborts_on_unresolved_admin_service(by_id):
    """(Not in the original handoff.) frontend-resolve-urls already aborts
    when the backend URL cannot be resolved; it must do the SAME for the
    admin service, matching deploy-all.sh:885-892's "an explicit channel was
    selected -> abort" rule (Cloud Build's _CHANNEL is always an explicit
    channel here). Silently falling back would leave
    /workspace/.vite_admin_api_base_url empty, and frontend-build-deploy
    would then ship a build whose firm-console calls become relative paths
    that Hosting's /api/** rewrite routes to the VOICE backend instead of
    the admin service.
    """
    body = script_of(by_id["frontend-resolve-urls"])
    assert "polyglot-admin" in body, (
        "frontend-resolve-urls no longer resolves the admin service URL"
    )
    admin_abort_idx = body.find('ADMIN_URL"')
    assert admin_abort_idx != -1 and "ABORT" in body[admin_abort_idx:], (
        "frontend-resolve-urls does not ABORT on an unresolved ADMIN_URL -- "
        "it would silently ship an empty VITE_ADMIN_API_BASE_URL instead"
    )


@pytest.mark.parametrize("channel", ["staging", "demo"])
def test_frontend_build_deploy_actually_exports_channel_at_runtime(by_id, channel, tmp_path):
    """RUNTIME half of test_frontend_build_exports_vite_app_channel: proves
    the export line is actually reached and evaluates to the right value,
    not merely present in the source text. Stubs npm/npx/cd's targets so the
    script runs to completion without a real Node toolchain or network
    Firebase deploy, and captures the environment at the point the (stubbed)
    npm is invoked.
    """
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover
        pytest.skip("bash not on PATH")

    script = script_of(by_id["frontend-build-deploy"])
    rendered = (
        script.replace("${_TARGET}", "frontend-" + channel)
        .replace("${_CHANNEL}", channel)
        # The real script reads its handoff files from Cloud Build's
        # fixed /workspace path; redirect that to tmp_path (bash's OWN
        # posix rendering of it) so this test does not need write access
        # to an actual /workspace.
        .replace("/workspace/", tmp_path.as_posix() + "/")
        .replace("$$", "$")
    )

    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".vite_ws_url").write_text("wss://example/ws/fill", encoding="utf-8")
    (tmp_path / ".vite_admin_api_base_url").write_text(
        "https://polyglot-admin-example.a.run.app", encoding="utf-8"
    )

    marker = tmp_path / "npm_env.txt"
    fake_npm = tmp_path / "npm"
    fake_npm.write_text(
        "#!/bin/bash\n"
        f'env > "{marker.as_posix()}"\n'
        "exit 0\n",
        encoding="utf-8", newline="\n",
    )
    fake_npm.chmod(0o755)
    fake_npx = tmp_path / "npx"
    fake_npx.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8", newline="\n")
    fake_npx.chmod(0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        f'cd "{tmp_path.as_posix()}"\n'
        'export PATH="$PWD:$PATH"\n'
        'export PROJECT_ID="test-project"\n'
        + rendered,
        encoding="utf-8", newline="\n",
    )

    result = subprocess.run(
        [bash, str(driver)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"frontend-build-deploy crashed for channel {channel!r}:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert marker.exists(), (
        f"frontend-build-deploy for channel {channel!r} never reached the "
        f"(stubbed) npm -- stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    env_text = marker.read_text(encoding="utf-8")
    assert f"VITE_APP_CHANNEL={channel}" in env_text, (
        f"npm's environment does not contain VITE_APP_CHANNEL={channel} -- "
        f"env dump:\n{env_text}"
    )
    assert "VITE_ADMIN_API_BASE_URL=https://polyglot-admin-example.a.run.app" in env_text, (
        "npm's environment does not contain the resolved "
        "VITE_ADMIN_API_BASE_URL"
    )


# --- sprint 23 PF-5 (bd polyglot-pdf-o2fub): the spend ceiling ---------------------------


def test_every_cloud_run_deploy_carries_a_max_instances_ceiling(steps):
    """The per-instance rate limiter (backend/utils/rate_limit.py) bounds one
    caller; --max-instances bounds what a flood can cost. Every `gcloud run
    deploy` in the build must carry it. Mutation: drop the flag from either
    deploy -> red, naming the step."""
    deploys = [s for s in steps if "gcloud run deploy" in script_of(s)]
    assert len(deploys) >= 2, [s.get("id") for s in deploys]
    missing = [s.get("id") for s in deploys if "--max-instances=" not in script_of(s)]
    assert missing == [], "Cloud Run deploy without a --max-instances ceiling: %s" % missing
