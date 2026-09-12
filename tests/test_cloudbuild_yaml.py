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

import os
import shutil
import subprocess
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
    """THREE suites, not the one someone remembers.

    The plan names backend + frontend + admin-console. A verify build that
    runs two of them still writes a success record, so every deploy target for
    that SHA proceeds on a partial test run.
    """
    backend = script_of(by_id["verify-backend"])
    assert "pytest" in backend
    for suite_root in ("backend/tests", "admin_backend/tests", "tests"):
        assert suite_root in backend, (
            f"the verify target's pytest run omits {suite_root}"
        )
    assert '-m "not external"' in backend, (
        "the verify run must exclude the flaky live-Gemini externals, matching "
        "CI -- those need real credentials the build does not have"
    )

    frontend = script_of(by_id["verify-frontend"])
    assert "cd frontend" in frontend and "npm test" in frontend
    assert "npm ci" in frontend

    console = script_of(by_id["verify-admin-console"])
    assert "cd admin-console" in console and "npm test" in console
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
    assert '--set-env-vars="$BACKEND_ENV"' in body
    assert '"${SECRETS_FLAG[@]}"' in body
    assert '"${SA_FLAG[@]}"' in body
    # The channel values must actually be appended, not merely read.
    assert 'BACKEND_ENV="$BACKEND_ENV,$CHANNEL_ENV"' in body


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


def test_admin_channel_file_matches_the_wrapper():
    """admin.env is declarative until bead polyglot-pdf-ywxoh wires it up.

    Two live copies of the same values is exactly the drift the channel files
    exist to end, so while BOTH exist they are pinned equal here. When 4.2
    switches deploy-admin.sh over to the file, this guard goes with the
    duplication.
    """
    admin = _parse_env_section(CHANNELS / "admin.env")
    wrapper = (REPO_ROOT / "deploy-admin.sh").read_text(encoding="utf-8")

    assert f'APP_MODULE="{admin["APP_MODULE"]}"' in wrapper, (
        "deploy-admin.sh and deploy/channels/admin.env disagree about "
        "APP_MODULE -- the admin service would serve a different app "
        "depending on which path deployed it"
    )
    for key in ("CORS_EXTRA_ORIGINS", "SWEEP_SCHEDULER_SA_EMAIL"):
        for origin in admin[key].split(";"):
            # SWEEP_SCHEDULER_SA_EMAIL embeds the project; the wrapper builds
            # it from $PROJECT, so compare the stable local part.
            needle = origin.split("@")[0] if "@" in origin else origin
            needle = needle.replace("polyglot-demo-aa709", "$PROJECT")
            assert needle in wrapper, (
                f"deploy/channels/admin.env declares {needle} for {key}, but "
                "deploy-admin.sh does not -- the two live copies have drifted"
            )
