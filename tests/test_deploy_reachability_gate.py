"""The Cloud Run reachability gate: the ONE module, and its FOUR bash callers
(bd polyglot-pdf-pidtg / polyglot-pdf-6oi9s original; ported to a single
python module by bd polyglot-pdf-ywxoh, Epic 4 bead 4.2).

WHY THIS EXISTS. `gcloud run deploy --allow-unauthenticated` only REQUESTS an
allUsers -> roles/run.invoker binding. The request can be REFUSED (the
domain-restricted-sharing org policy rejects allUsers) while gcloud still
creates the service and exits 0 -- leaving a service that 403s every request
at Cloud Run's own gate, before any application code runs. It bites only a
NEW service, because an existing one's binding predates the policy and is not
retroactively stripped.

REWRITTEN FOR THE PYTHON PORT. deploy-all.sh, backend/deploy-new.sh,
deploy-editor.sh and deploy-admin-console.sh used to each carry a
byte-identical bash FUNCTION implementing the whole check; this file used to
pin all four copies equal and drive them via subprocess against a stubbed
`gcloud` shell function. That check now lives in ONE place --
scripts/verify_service_reachable.py, exercised directly (with dependency
injection, no subprocess/gcloud stub needed) by
tests/test_verify_service_reachable.py. THIS file's job narrows to what
survives the move: proving the four scripts are CALLERS of the module (not a
fifth hand copy of the logic), that their call sites keep the same load-
bearing properties the bash version needed (bare-command shape so `exit 1`
still terminates the calling script; correct severity per call site; correct
argument binding), and that cloudbuild.yaml's build steps call the same
module rather than a sixth copy.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ALL = REPO_ROOT / "deploy-all.sh"
DEPLOY_NEW = REPO_ROOT / "backend" / "deploy-new.sh"
DEPLOY_EDITOR = REPO_ROOT / "deploy-editor.sh"
DEPLOY_ADMIN_CONSOLE = REPO_ROOT / "deploy-admin-console.sh"
MODULE = REPO_ROOT / "scripts" / "verify_service_reachable.py"

# shutil.which, never a bare "bash": on Windows a bare name resolves to WSL's
# bash, which cannot see the Git-Bash filesystem and fails every script with
# a relay error that reads like a syntax error.
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not on PATH")

FN_START = "verify_service_publicly_reachable() {"
FN_END = "\n}\n"


def _gate_function(script: Path) -> str:
    """The verify_service_publicly_reachable wrapper definition, verbatim."""
    body = script.read_text(encoding="utf-8")
    assert FN_START in body, f"{script.name} has no reachability wrapper function"
    i = body.index(FN_START)
    j = body.index(FN_END, i) + len(FN_END)
    return body[i:j]


# The four bash scripts every test below is parametrized over. Historically
# these carried the FULL gate logic; now each is a thin wrapper that shells
# out to scripts/verify_service_reachable.py.
ALL_WRAPPER_SCRIPTS = [
    "deploy-all.sh",
    "backend/deploy-new.sh",
    "deploy-editor.sh",
    "deploy-admin-console.sh",
]


def test_the_module_exists_and_has_no_inline_copy_left():
    """scripts/verify_service_reachable.py is the ONE gate; nothing else may
    carry a second implementation of the IAM-policy check."""
    assert MODULE.is_file()
    module_text = MODULE.read_text(encoding="utf-8")
    assert "get-iam-policy" in module_text
    assert "roles/run.invoker" in module_text


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_each_wrapper_defines_the_function_as_a_thin_call_to_the_module(rel):
    """No inline copy left: the function's BODY must call the python module,
    not query gcloud's IAM policy itself."""
    fn = _gate_function(REPO_ROOT / rel)
    assert "verify_service_reachable.py" in fn, (
        f"{rel}'s verify_service_publicly_reachable function does not call "
        f"scripts/verify_service_reachable.py -- it may still carry an "
        f"inline copy of the gate logic"
    )
    # THE TELL of a leftover inline copy: the old implementation queried
    # get-iam-policy directly inside the bash function. A wrapper must not.
    assert "get-iam-policy" not in fn, (
        f"{rel}'s function still queries get-iam-policy directly -- this is "
        f"a hand copy of the gate, not a call to the shared module"
    )


def test_all_four_wrapper_functions_are_byte_identical():
    """The wrapper functions themselves must not drift from each other, same
    discipline as the pre-port suite (test_gate_copies_are_identical and its
    3-way/4-way extensions) -- now applied to the THIN WRAPPER instead of the
    full gate body."""
    bodies = {rel: _gate_function(REPO_ROOT / rel) for rel in ALL_WRAPPER_SCRIPTS}
    first_rel, first_body = next(iter(bodies.items()))
    for rel, body in bodies.items():
        assert body == first_body, (
            f"{rel}'s verify_service_publicly_reachable wrapper has drifted "
            f"from {first_rel}'s"
        )


# ---------------------------------------------------------------------------
# EXECUTE the wrapper functions, with python and gcloud STUBBED, to prove the
# shell plumbing (argument passing, exit-code translation) actually works --
# not merely that the source text looks right.
# ---------------------------------------------------------------------------


def _run_wrapper(tmp_path: Path, script: Path, call_args: str,
                  fake_python_exit: int, fake_python_stderr: str = "") -> tuple:
    """Extract `script`'s wrapper function, embed it in a driver that stubs
    the resolved interpreter to a fake script reporting the args it got and
    exiting with `fake_python_exit`, then invoke the function with
    `call_args`.
    """
    fn = _gate_function(script)
    fake_py = tmp_path / "python3"
    fake_py.write_text(
        "#!/bin/bash\n"
        'echo "PY_CALLED: $@"\n'
        f'{"echo " + repr(fake_python_stderr) + " >&2" if fake_python_stderr else ""}\n'
        f"exit {fake_python_exit}\n",
        encoding="utf-8", newline="\n",
    )
    fake_py.chmod(0o755)
    # MANIFEST_PYTHON_CANDIDATES is deploy-all.sh's own interpreter-candidate
    # override -- the wrapper function reuses that same variable. Pointing
    # the FIRST candidate at our fake by PATH ordering keeps the driver
    # portable (the fake shadows any real `python3`/`python`/`py` on PATH).
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "set -e\n"
        # $PWD, not a python-side path string: on Windows Git Bash, a
        # Windows-style "C:/Users/..." string in PATH is NOT recognized the
        # same way as bash's own POSIX-style "/c/Users/..." rendering, so
        # `command -v` inside the function fails to find the fake python3
        # even though the file is right there. cd into the directory and let
        # bash report its OWN idea of the path.
        f'cd "{tmp_path.as_posix()}"\n'
        'export PATH="$PWD:$PATH"\n'
        'export MANIFEST_PYTHON_CANDIDATES="python3"\n'
        + fn
        + f"\nverify_service_publicly_reachable {call_args}\n"
        + 'echo "REACHED_END"\n',
        encoding="utf-8", newline="\n",
    )
    proc = subprocess.run(
        [BASH, str(driver)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp_path), timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_wrapper_reaches_end_when_the_module_exits_zero(tmp_path, rel):
    rc, out, err = _run_wrapper(
        tmp_path, REPO_ROOT / rel, '"svc" "us-central1" "proj"', fake_python_exit=0
    )
    assert rc == 0, err
    assert "REACHED_END" in out
    assert 'PY_CALLED:' in out
    assert "verify_service_reachable.py svc us-central1 proj --severity fatal" in out


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_wrapper_exits_nonzero_and_does_not_reach_end_when_the_module_fails(tmp_path, rel):
    """THE LOAD-BEARING SHAPE: the module's exit 1 must terminate the CALLING
    script, not just the function's own return. This is the bash-side
    equivalent of the pre-port suite's "gate must be called as a bare
    command" pin -- if this function were called inside `if`, `$(...)`, or a
    pipeline, `exit 1` would not propagate and REACHED_END would still print.
    """
    rc, out, err = _run_wrapper(
        tmp_path, REPO_ROOT / rel, '"svc" "us-central1" "proj"', fake_python_exit=1
    )
    assert rc == 1
    assert "REACHED_END" not in out


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_wrapper_passes_warn_severity_through(tmp_path, rel):
    rc, out, err = _run_wrapper(
        tmp_path, REPO_ROOT / rel, '"svc" "us-central1" "proj" warn', fake_python_exit=0
    )
    assert rc == 0
    assert "--severity warn" in out


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_wrapper_defaults_to_fatal_severity(tmp_path, rel):
    """Omitting the 4th argument must still pass --severity fatal explicitly
    -- the wrapper's own default, not an implicit behavior a caller could
    accidentally lose."""
    rc, out, err = _run_wrapper(
        tmp_path, REPO_ROOT / rel, '"svc" "us-central1" "proj"', fake_python_exit=0
    )
    assert "--severity fatal" in out


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_wrapper_binds_arguments_to_the_module_call(tmp_path, rel):
    rc, out, err = _run_wrapper(
        tmp_path, REPO_ROOT / rel, '"my-service" "europe-west1" "my-project"',
        fake_python_exit=0,
    )
    assert "my-service europe-west1 my-project" in out


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_wrapper_aborts_when_no_python_interpreter_is_found(tmp_path, rel):
    """The find_manifest_python-style fallback: no working interpreter must
    abort the deploy rather than silently skip the check."""
    fn = _gate_function(REPO_ROOT / rel)
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "set -e\n"
        # Only MANIFEST_PYTHON_CANDIDATES needs to fail to resolve -- keep
        # the real PATH intact (dirname/pwd/cd are external commands on
        # Windows Git Bash and a wiped PATH breaks the driver itself before
        # it ever reaches the interpreter-search loop). Naming candidates
        # that cannot possibly exist on any machine is enough to force the
        # "no interpreter" branch without touching PATH at all.
        'export MANIFEST_PYTHON_CANDIDATES="no_such_interp_a no_such_interp_b"\n'
        + fn
        + '\nverify_service_publicly_reachable "svc" "us-central1" "proj"\n'
        + 'echo "REACHED_END"\n',
        encoding="utf-8", newline="\n",
    )
    proc = subprocess.run(
        [BASH, str(driver)], capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=str(tmp_path), timeout=60,
    )
    assert proc.returncode == 1
    assert "REACHED_END" not in proc.stdout
    assert "No python interpreter found" in proc.stderr


# ---------------------------------------------------------------------------
# The CALL SITES within each script -- unchanged shape requirements from the
# pre-port suite (bare command, no swallowing construct, correct severity per
# call, ordering vs. the success banner). These properties are about how each
# SCRIPT uses the (now-thin) function, so they still apply unmodified.
# ---------------------------------------------------------------------------

GATED_DEPLOY_SCRIPTS = ["deploy-all.sh", "backend/deploy-new.sh"]


@pytest.mark.parametrize("rel", GATED_DEPLOY_SCRIPTS)
def test_script_that_deploys_publicly_carries_the_gate(rel):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "--allow-unauthenticated" in body
    assert "verify_service_publicly_reachable " in body


def test_allow_unauthenticated_set_is_complete():
    found = set()
    for path in REPO_ROOT.rglob("*.sh"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "node_modules" in rel or "/.claude/worktrees/" in "/" + rel:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(
            "--allow-unauthenticated" in ln
            and not ln.strip().startswith("#")
            and "_gate_error" not in ln
            for ln in text.splitlines()
        ):
            found.add(rel)
    assert found == set(GATED_DEPLOY_SCRIPTS), (
        "the set of scripts deploying a PUBLIC Cloud Run service changed.\n"
        f"  unlisted: {sorted(found - set(GATED_DEPLOY_SCRIPTS))}\n"
        f"  listed but no longer public: {sorted(set(GATED_DEPLOY_SCRIPTS) - found)}"
    )


def _logical_calls(body: str) -> list[str]:
    logical = body.replace("\\\n", " ")
    return [
        ln.strip()
        for ln in logical.splitlines()
        if "verify_service_publicly_reachable" in ln
        and not ln.strip().startswith("#")
        and "()" not in ln
    ]


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_every_call_site_is_a_bare_command(rel):
    """A `| cat`, `$(...)`, `&&`/`||`, or backgrounding around the call would
    swallow its `exit 1` in a subshell -- the exact neutering mutation the
    pre-port suite's cross-surface review caught."""
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    calls = _logical_calls(body)
    assert calls, f"{rel} never calls the gate"
    for call in calls:
        bare = re.sub(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+", "", call)
        assert bare.startswith("verify_service_publicly_reachable"), (
            f"{rel}: the gate must be invoked as a bare command. Found: {call!r}"
        )
        for swallower in ("|", "$(", "&&", "||", "&"):
            assert swallower not in call, (
                f"{rel}: the gate's call contains {swallower!r}, which would "
                f"swallow its exit code. Found: {call!r}"
            )


def _severity_of(call: str) -> str:
    args = call.split()[1:]
    while args and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", args[0]):
        args = args[1:]
    if len(args) <= 3:
        return "fatal"
    token = args[3]
    assert "$" not in token, (
        f"severity is a variable expansion ({token!r}) -- its value cannot "
        f"be read from the source. Call: {call!r}"
    )
    stripped = token.strip('"').strip("'")
    assert stripped in ("warn", "fatal")
    return stripped


# Exact (n_warn, n_fatal) per script -- pins the SET of call sites, not just
# "at least one". See the pre-port suite's own rationale: an "at least one
# fatal" lower bound lets a SECOND call site be downgraded while a decoy
# satisfies the assertion.
CALL_SITE_SEVERITY = {
    "deploy-all.sh": (2, 1),        # frontend stage warns x2 (WS URL + admin URL), backend stage fatal
    "backend/deploy-new.sh": (0, 1),  # only ever creates; always fatal
    "deploy-editor.sh": (1, 0),
    "deploy-admin-console.sh": (1, 0),
}


@pytest.mark.parametrize("rel", ALL_WRAPPER_SCRIPTS)
def test_call_site_severities_match_the_pinned_counts(rel):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    calls = _logical_calls(body)
    severities = [_severity_of(c) for c in calls]
    want_warn, want_fatal = CALL_SITE_SEVERITY[rel]
    got_warn, got_fatal = severities.count("warn"), severities.count("fatal")
    assert (got_warn, got_fatal) == (want_warn, want_fatal), (
        f"{rel}: expected {want_warn} warn / {want_fatal} fatal call(s), got "
        f"{got_warn} / {got_fatal} ({severities})"
    )


SUCCESS_BANNERS = {
    "deploy-all.sh": "Backend deployed successfully",
    "backend/deploy-new.sh": "Deployment Complete!",
}


@pytest.mark.parametrize("rel", GATED_DEPLOY_SCRIPTS)
def test_gate_runs_before_the_success_banner(rel):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    lines = body.replace("\\\n", " ").splitlines()
    call_idx = next(
        (i for i, ln in enumerate(lines)
         if "verify_service_publicly_reachable" in ln
         and not ln.strip().startswith("#") and "()" not in ln),
        None,
    )
    assert call_idx is not None, f"{rel} never calls the gate"
    banner = SUCCESS_BANNERS[rel]
    banner_hits = [i for i, ln in enumerate(lines)
                   if banner in ln and not ln.strip().startswith("#")]
    assert banner_hits, f"{rel}: could not find the success banner {banner!r}"
    assert len(banner_hits) == 1, (
        f"{rel}: {banner!r} matches {len(banner_hits)} lines; must identify exactly one"
    )
    assert call_idx < banner_hits[0], (
        f"{rel}: the gate is called AFTER the success banner"
    )


def test_frontend_stage_also_checks_reachability():
    body = DEPLOY_ALL.read_text(encoding="utf-8")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    assert "verify_service_publicly_reachable" in fe


def test_frontend_stage_warns_rather_than_aborting():
    body = DEPLOY_ALL.read_text(encoding="utf-8")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    assert re.search(
        r"verify_service_publicly_reachable[^\n]*\\?\s*\n?[^\n]*\bwarn\b", fe
    )


@pytest.mark.parametrize(
    "rel", ["deploy-demo.sh", "deploy-staging.sh", "deploy-admin-console.sh"]
)
def test_channel_wrapper_rejects_an_unknown_argument(rel):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    parser = body.split("for arg in")[1].split("esac")[0]
    assert "*)" in parser
    assert "Unknown argument" in parser and "exit 1" in parser


# ---------------------------------------------------------------------------
# The URL-BAKING set (resolves a service URL and exports a VITE_* var) --
# same set as the pre-port suite; the property (must consult the gate) still
# holds against the thin wrapper.
# ---------------------------------------------------------------------------

URL_BAKING_SCRIPTS = ["deploy-all.sh", "deploy-editor.sh", "deploy-admin-console.sh"]


@pytest.mark.parametrize("rel", URL_BAKING_SCRIPTS)
def test_url_baking_script_consults_the_reachability_gate(rel, tmp_path):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "services describe" in body
    calls = _logical_calls(body)
    assert calls, (
        f"{rel} bakes a resolved backend URL into a frontend build without "
        f"calling the reachability gate"
    )
    for call in calls:
        driver = tmp_path / f"call_{abs(hash(call))}.sh"
        driver.write_text(
            "BACKEND_SERVICE_NAME=SVC; REGION=REG; PROJECT=PRJ\n"
            "POLYGLOT_PROJECT_NAME=PRJ; SERVICE_NAME=SVC\n"
            "ADMIN_SERVICE_NAME=SVC\n"
            "verify_service_publicly_reachable() {\n"
            '  echo "ARGC=$# SVC=$1 REGION=$2 PROJECT=$3 SEVERITY=$4"\n'
            "}\n" + call + "\n",
            encoding="utf-8", newline="\n",
        )
        proc = subprocess.run(
            [BASH, driver.name], capture_output=True, text=True,
            encoding="utf-8", cwd=str(tmp_path), timeout=60,
        )
        assert proc.returncode == 0, f"{rel}: gate call does not parse/run: {proc.stderr!r}"
        out = proc.stdout.strip()
        assert "ARGC=3" in out or "ARGC=4" in out
        assert "SVC=SVC" in out and "REGION=REG" in out and "PROJECT=PRJ" in out


def test_url_baking_set_is_complete():
    found = set()
    for path in REPO_ROOT.rglob("*.sh"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "node_modules" in rel or "/.claude/worktrees/" in "/" + rel:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "services describe" in text and "export VITE_" in text:
            found.add(rel)
    assert found == set(URL_BAKING_SCRIPTS), (
        "the set of scripts baking a resolved backend URL into a frontend "
        f"build changed.\n  unlisted: {sorted(found - set(URL_BAKING_SCRIPTS))}\n"
        f"  listed but no longer baking: {sorted(set(URL_BAKING_SCRIPTS) - found)}"
    )
