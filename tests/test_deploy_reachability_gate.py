"""The Cloud Run reachability gate: behavior, and the COMPLETE set of gated
scripts (bd polyglot-pdf-pidtg, extended by bd polyglot-pdf-6oi9s).

WHY THIS EXISTS. `gcloud run deploy --allow-unauthenticated` only REQUESTS an
allUsers -> roles/run.invoker binding. The request can be REFUSED (the
domain-restricted-sharing org policy rejects allUsers) while gcloud still
creates the service and exits 0 -- leaving a service that 403s every request at
Cloud Run's own gate, before any application code runs. It bites only a NEW
service, because an existing one's binding predates the policy and is not
retroactively stripped.

WHAT THIS FILE PINS, AND WHY IT RUNS THE SHELL. The sibling
test_deploy_channel_isolation.py asserts on deploy-all.sh's TEXT, which is all
you can do for wiring. Here the gate is a self-contained function, so these
tests EXECUTE it against synthetic gcloud output -- a text assertion cannot tell
you that `roles/run.viewer` is rejected while `roles/run.invoker` is accepted.
Mirrors tests/test_deploy_manifest_validation.py, which extracts and runs the
manifest helpers the same way.

The gate was wrong in BOTH directions before it was right, so both are pinned:
  - FALSE PASS: a raw-text grep for "allUsers" accepted allUsers on any role.
  - FALSE FAIL: --filter without --flatten ';'-joined every role onto one line,
    so a service with a SECOND binding was wrongly rejected.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ALL = REPO_ROOT / "deploy-all.sh"
DEPLOY_NEW = REPO_ROOT / "backend" / "deploy-new.sh"
# shutil.which, never a bare "bash": on Windows a bare name resolves to WSL's
# bash, which cannot see the Git-Bash filesystem (mirrors
# tests/test_deploy_manifest_validation.py).
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not on PATH")

FN_START = "# Verify a just-deployed Cloud Run service is PUBLICLY REACHABLE"
FN_END = "\n}\n"


def _gate_function(script: Path) -> str:
    """The verify_service_publicly_reachable definition, verbatim."""
    body = script.read_text(encoding="utf-8")
    assert FN_START in body, f"{script.name} has no reachability gate function"
    i = body.index(FN_START)
    j = body.index(FN_END, i) + len(FN_END)
    return body[i:j]


def _run_gate(tmp_path: Path, policy: list[tuple[str, str]], gcloud_rc: int = 0):
    """Execute the gate against a synthetic IAM policy, and report its exit code.

    `policy` is a list of (role, member) pairs, i.e. what the service's IAM
    policy actually contains.

    THE STUB EMULATES gcloud's PROJECTION, it does not hand back a canned
    answer. That distinction is load-bearing: a stub that always returns
    pre-flattened output cannot notice a missing --flatten, so the false-FAIL
    regression (see test_allusers_on_invoker_among_several_bindings_passes)
    would sail past it. Instead the stub inspects the flags it was called with
    and reproduces gcloud's real behavior:

      WITH --flatten:    each member/role pair is its own record, so --filter is
                         per-binding and each surviving role prints on its OWN
                         LINE.
      WITHOUT --flatten: --filter applies to the WHOLE policy resource, and
                         value(bindings.role) emits every role ';'-joined on ONE
                         line -- which is exactly what broke grep -qx.

    Verified against real gcloud 579.0.0 output before being encoded here.
    """
    # gcloud is stubbed as a SHELL FUNCTION, not a file on PATH. Python's
    # os.pathsep is ";" on Windows while bash expects ":", so a PATH-based stub
    # silently fails to shadow the real gcloud -- every case would then run the
    # live CLI and the tests would be meaningless. A function override needs no
    # PATH manipulation and behaves identically on every platform.
    flattened = "\n".join(r for r, m in policy if m == "allUsers")
    joined = ";".join(r for r, _ in policy)
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "gcloud() {\n"
        '  if [[ "$*" == *"--flatten"* ]]; then\n'
        f"    cat <<'FLATEOF'\n{flattened}\nFLATEOF\n"
        "  else\n"
        f"    cat <<'JOINEOF'\n{joined}\nJOINEOF\n"
        "  fi\n"
        f"  return {gcloud_rc}\n"
        "}\n"
        + _gate_function(DEPLOY_ALL)
        + '\nverify_service_publicly_reachable "svc" "us-central1" "proj"\n'
        + 'echo "REACHED_END"\n',
        encoding="utf-8",
        newline="\n",
    )
    proc = subprocess.run(
        [BASH, "driver.sh"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# Behavior: the gate's decision on real-shaped gcloud output.
# ---------------------------------------------------------------------------


def test_allusers_on_invoker_passes(tmp_path):
    """The healthy case must not block a deploy."""
    rc, out, _ = _run_gate(tmp_path, [("roles/run.invoker", "allUsers")])
    assert rc == 0 and "REACHED_END" in out


def test_allusers_on_invoker_among_several_bindings_passes(tmp_path):
    """THE FALSE-FAIL CASE. --flatten puts one role per line.

    Without --flatten, gcloud ';'-joins every role onto ONE line and grep -qx
    matches nothing -- so a service with an operator's roles/run.admin, or a
    service-to-service invoker, was wrongly refused. Both live services happened
    to carry exactly one binding, so this would not have surfaced until it
    blocked a real deploy.
    """
    rc, out, _ = _run_gate(
        tmp_path,
        [("roles/run.invoker", "allUsers"),
         ("roles/run.admin", "user:josh@example.com")],
    )
    assert rc == 0 and "REACHED_END" in out, (
        "a service with MORE than one binding must still pass when allUsers is "
        "bound to roles/run.invoker"
    )


def test_no_bindings_at_all_aborts(tmp_path):
    """The original bug: the binding was refused, so nothing is bound."""
    rc, out, err = _run_gate(tmp_path, [])
    assert rc == 1, "an unreachable service must abort the deploy"
    assert "REACHED_END" not in out
    assert "NOT publicly reachable" in err
    assert "add-iam-policy-binding" in err, "the failure must name the remedy"


def test_allusers_on_a_non_invoker_role_aborts(tmp_path):
    """THE FALSE-PASS CASE.

    A raw-text grep for "allUsers" accepted this: allUsers bound to some
    unrelated role, while the INVOKER binding was missing and the service still
    403'd everything -- the very bug the gate exists to catch, reported green.
    """
    rc, _, err = _run_gate(
        tmp_path,
        [("roles/run.viewer", "allUsers"),
         ("roles/run.invoker", "serviceAccount:x@y.iam.gserviceaccount.com")],
    )
    assert rc == 1, (
        "allUsers on a NON-invoker role leaves the service un-invokable and "
        "must abort"
    )
    assert "NOT publicly reachable" in err


def test_lookalike_role_name_aborts(tmp_path):
    """grep -qx is an EXACT line match; a substring match would accept this."""
    rc, _, _ = _run_gate(tmp_path, [("roles/run.invoker.custom", "allUsers")])
    assert rc == 1


def test_failed_iam_read_warns_and_continues(tmp_path):
    """Being unable to CHECK is not proof the service is broken.

    A gate that aborts on an inconclusive read is its own false alarm, and a
    gate that cries wolf gets deleted -- taking the real check with it.
    """
    rc, out, err = _run_gate(
        tmp_path, [("roles/run.invoker", "allUsers")], gcloud_rc=1
    )
    assert rc == 0, "an inconclusive IAM read must not abort the deploy"
    assert "REACHED_END" in out
    assert "skipping the" in err, "it must say the check was skipped"


# ---------------------------------------------------------------------------
# The SET: every script that passes --allow-unauthenticated must be gated.
# ---------------------------------------------------------------------------

# scar #8 (ENUMERATE THE SET). pidtg fixed deploy-all.sh; the set had TWO
# members and backend/deploy-new.sh -- the script whose entire job is the
# new-service case that actually triggers the bug -- stayed ungated for a
# further PR. Pin the SET so a THIRD such script fails CI instead of shipping.
GATED_DEPLOY_SCRIPTS = ["deploy-all.sh", "backend/deploy-new.sh"]


@pytest.mark.parametrize("rel", GATED_DEPLOY_SCRIPTS)
def test_script_that_deploys_publicly_carries_the_gate(rel):
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "--allow-unauthenticated" in body, (
        f"{rel} is listed as a public-deploy script but no longer passes "
        f"--allow-unauthenticated; remove it from GATED_DEPLOY_SCRIPTS."
    )
    assert "verify_service_publicly_reachable " in body, (
        f"{rel} deploys a service publicly but never CALLS the reachability "
        f"gate, so it can report success over a service that 403s everything."
    )


def test_gate_copies_are_identical():
    """The MUST-match contract between the two copies.

    The repo has no shared shell library (see the manifest helpers, duplicated
    the same way and pinned by tests/test_deploy_manifest_validation.py), so
    byte-identity is what stops the two gates drifting apart -- and a drifted
    gate is one that is subtly weaker in one script than the other.
    """
    assert _gate_function(DEPLOY_ALL) == _gate_function(DEPLOY_NEW)


def test_allow_unauthenticated_set_is_complete():
    """Pins the SET, not its members.

    A NEW script passing --allow-unauthenticated must be added to
    GATED_DEPLOY_SCRIPTS (and gated), not silently escape the check.
    """
    found = set()
    for path in REPO_ROOT.rglob("*.sh"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "node_modules" in rel or "/.claude/worktrees/" in "/" + rel:
            continue
        try:
            if "--allow-unauthenticated" in path.read_text(encoding="utf-8"):
                found.add(rel)
        except (OSError, UnicodeDecodeError):
            continue
    assert found == set(GATED_DEPLOY_SCRIPTS), (
        "the set of scripts deploying a PUBLIC Cloud Run service changed.\n"
        f"  unlisted (gate them, then add them): "
        f"{sorted(found - set(GATED_DEPLOY_SCRIPTS))}\n"
        f"  listed but no longer public: "
        f"{sorted(set(GATED_DEPLOY_SCRIPTS) - found)}"
    )


def test_gcloud_stderr_cannot_satisfy_the_check(tmp_path):
    """Noise on stderr must not be able to answer the question.

    A gcloud component-update nag or deprecation notice mentioning the matched
    text must never make an unreachable service look reachable. stderr belongs
    on the operator's terminal; only the parsed value drives the decision.

    HONEST NOTE ON WHAT THIS DOES AND DOES NOT PROVE. Two independent things
    protect this, and only one of them is load-bearing:

      1. The query does not merge stderr (`2>&1`) into the captured value.
      2. `grep -qx` demands the WHOLE line be exactly "roles/run.invoker".

    (2) alone defeats every realistic stderr line, because a warning always
    carries surrounding text. So this test still passes if (1) is removed -- I
    verified that by mutation rather than assuming otherwise, after initially
    claiming this case was fully covered when it was not.

    It is kept because it pins the OUTCOME that matters (stderr noise never
    yields a false PASS) across either implementation, and it would catch a
    future loosening of grep -qx combined with a merged stderr -- the pair that
    actually reintroduces the hole. The `2>&1` absence itself is a code-shape
    detail, deliberately not pinned separately.
    """
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "gcloud() {\n"
        '  echo "WARNING: roles/run.invoker updates are available." >&2\n'
        "  return 0\n"
        "}\n"
        + _gate_function(DEPLOY_ALL)
        + '\nverify_service_publicly_reachable "svc" "us-central1" "proj"\n'
        + 'echo "REACHED_END"\n',
        encoding="utf-8",
        newline="\n",
    )
    proc = subprocess.run(
        [BASH, "driver.sh"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
        timeout=60,
    )
    assert proc.returncode == 1, (
        "a stderr notice mentioning roles/run.invoker must NOT satisfy the "
        "check -- the query must not merge stderr into the captured value"
    )
    assert "REACHED_END" not in proc.stdout


def _run_gate_with_helpers(tmp_path: Path):
    """Run the gate in a shell that DEFINES log_warn/log_error, as deploy-all.sh does."""
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "YELLOW=$'\033[1;33m'; RED=$'\033[0;31m'; NC=$'\033[0m'\n"
        'log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }\n'
        'log_error() { echo -e "${RED}[ERROR]${NC} $1"; }\n'
        "gcloud() { echo \"\"; return 0; }\n"
        + _gate_function(DEPLOY_ALL)
        + '\nverify_service_publicly_reachable "svc" "r" "p"\n',
        encoding="utf-8",
        newline="\n",
    )
    proc = subprocess.run(
        [BASH, "driver.sh"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_gate_reuses_the_callers_log_helpers_when_they_exist(tmp_path):
    """deploy-all.sh must keep its coloured [ERROR] on STDOUT, as before.

    Extracting the gate into a helper-free function silently moved deploy-all.sh's
    warnings from stdout (coloured, via log_warn/log_error) to plain stderr --
    caught in review. A wrapper capturing only stdout would have lost them, and
    "behavior-preserving" would have been false.

    The function now delegates to log_warn/log_error WHEN THEY ARE DEFINED and
    falls back to stderr otherwise, so it stays self-contained for
    backend/deploy-new.sh (which defines neither) without changing deploy-all.sh.
    """
    rc, out, err = _run_gate_with_helpers(tmp_path)
    assert rc == 1
    assert "DEPLOY FAILED" in out, (
        "with log_error defined, the gate's message must go to STDOUT via it -- "
        "not to stderr, which is where the helper-free fallback writes"
    )
    assert "\033" in out, "log_error's colour must survive the delegation"


def test_gate_falls_back_to_stderr_without_log_helpers(tmp_path):
    """backend/deploy-new.sh defines no log_* helpers and must still report."""
    rc, out, err = _run_gate(tmp_path, [])
    assert rc == 1
    assert "DEPLOY FAILED" in err, (
        "without log_error, the gate must still emit its message (on stderr)"
    )


# ---------------------------------------------------------------------------
# The CALL SITES, not just the gate's presence.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", GATED_DEPLOY_SCRIPTS)
def test_gate_is_called_as_a_bare_command(rel):
    """The call must not sit in a subshell, pipeline, or conditional.

    THE NEUTERING MUTATION (found by the pre-PR cross-surface review): appending
    `| cat` to the call puts the function in a SUBSHELL, so its `exit 1` kills
    only that subshell and the script sails on to "Deployment Complete!" and
    exits 0 -- reintroducing the exact bug this gate exists to prevent, past a
    fully green suite. The same applies to `if ...`, `... || true`, and
    `$(...)`: `exit` only terminates the shell it runs in.

    Deleting the call outright was already caught. This pins the SHAPE of the
    surviving call, which is the part that can be broken while still looking
    present.

    LINE CONTINUATIONS ARE JOINED FIRST, and that is not a detail. The first
    version of this test split on raw lines, so deploy-all.sh's call --

        verify_service_publicly_reachable \\
            "$BACKEND_SERVICE_NAME" "$REGION" "$POLYGLOT_PROJECT_NAME"

    -- was only ever inspected as `verify_service_publicly_reachable \\`. The
    ARGUMENTS line, which is exactly where a neutering `| cat` would go, was
    invisible. So the guard protected deploy-new.sh and left deploy-all.sh --
    the script already written in the vulnerable shape -- unguarded. A second
    review round caught it by appending `| cat` there and watching all 15 tests
    pass while the deploy reported success over an unreachable service.

    Fixing one member of a set and believing the set is done is scar #8; doing
    it inside the very test written to prevent that is worth the extra comment.
    """
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    # Join backslash continuations so each call is ONE logical line.
    logical = body.replace("\\\n", " ")
    calls = [
        ln.strip()
        for ln in logical.splitlines()
        if "verify_service_publicly_reachable" in ln
        and not ln.strip().startswith("#")
        and "()" not in ln  # the definition itself
    ]
    assert calls, f"{rel} never calls the gate"
    for call in calls:
        # A leading `VAR=value ` prefix is ALLOWED and is not a subshell: bash
        # applies it to the command's environment for that one invocation, and
        # an `exit` inside still terminates the script (verified, not assumed).
        # The frontend stage uses exactly this to select warn mode
        # (bd polyglot-pdf-816te). Everything the loop below rejects -- pipes,
        # command substitution, `&&`/`||` guards, backgrounding -- genuinely does
        # run the function somewhere its `exit 1` cannot reach the script.
        bare = re.sub(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+", "", call)
        assert bare.startswith("verify_service_publicly_reachable"), (
            f"{rel}: the gate must be invoked as a BARE command (optionally with "
            f"a VAR=value environment prefix), not inside a conditional or "
            f"assignment -- `exit 1` would not terminate the script. "
            f"Found: {call!r}"
        )
        for swallower in ("|", "$(", "&&", "||", "&"):
            assert swallower not in call, (
                f"{rel}: the gate's call contains {swallower!r}, which runs it "
                f"in a subshell or guards it -- its `exit 1` would be swallowed "
                f"and the deploy would report success over an unreachable "
                f"service. Found: {call!r}"
            )


# The EXACT success banner each gated script must not print for an unreachable
# service. These are full, distinctive substrings on purpose.
#
# A looser pair of conditions ('log_success "' AND "deployed successfully") was
# a VACUOUS-PASS trap: deploy-all.sh has THREE such banners -- backend (the one
# the gate must precede), form-kits, and frontend. Taking the FIRST match meant
# rewording the backend banner silently fell through to the form-kits one 117
# lines later, and the ordering assertion then held for almost any gate
# placement. The `banner_idx is not None` check, whose whole job was to make a
# rewording fail LOUDLY, was itself satisfied by the wrong banner.
# (Found by the pre-PR cross-surface review, round 3.)
SUCCESS_BANNERS = {
    "deploy-all.sh": "Backend deployed successfully",
    "backend/deploy-new.sh": "Deployment Complete!",
}


@pytest.mark.parametrize("rel", GATED_DEPLOY_SCRIPTS)
def test_gate_runs_before_the_success_banner(rel):
    """Ordering is load-bearing, and the comments say so -- so pin it.

    backend/deploy-new.sh's own comment reads: "Runs BEFORE the success banner:
    a service that 403s everything must never be reported as 'Deployment
    Complete'." Nothing enforced that. Moving the call BELOW the banner left the
    suite fully green while the operator saw success printed first and only then
    an abort -- code contradicting its own comment, with the comment asserting a
    guarantee no test held (found by the pre-PR cross-surface review).
    """
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    # A REAL continuation join (backslash-newline), not the literal two-character
    # "\\n" this line first contained -- which matched nothing and silently made
    # the join a no-op, the very defect this guard's sibling was added to fix.
    lines = body.replace("\\\n", " ").splitlines()

    call_idx = next(
        (
            i
            for i, ln in enumerate(lines)
            if "verify_service_publicly_reachable" in ln
            and not ln.strip().startswith("#")
            and "()" not in ln
        ),
        None,
    )
    assert call_idx is not None, f"{rel} never calls the gate"

    banner = SUCCESS_BANNERS[rel]
    banner_hits = [
        i
        for i, ln in enumerate(lines)
        if banner in ln and not ln.strip().startswith("#")
    ]
    assert banner_hits, (
        f"{rel}: could not find the success banner {banner!r}. If its wording "
        f"changed, update SUCCESS_BANNERS -- do NOT loosen the match, which is "
        f"what made this guard pass vacuously before."
    )
    assert len(banner_hits) == 1, (
        f"{rel}: {banner!r} matches {len(banner_hits)} lines "
        f"{[i + 1 for i in banner_hits]}. The banner substring must identify "
        f"EXACTLY the one the gate has to precede -- with several matches this "
        f"guard silently compares against the wrong one."
    )
    banner_idx = banner_hits[0]
    assert call_idx < banner_idx, (
        f"{rel}: the reachability gate is called AFTER the success banner "
        f"(line {call_idx + 1} vs {banner_idx + 1}). A service that 403s every "
        f"request would be reported as a successful deploy before the abort."
    )


# ---------------------------------------------------------------------------
# The FRONTEND stage must check reachability too (bd polyglot-pdf-816te).
# ---------------------------------------------------------------------------


def test_frontend_stage_also_checks_reachability():
    """A frontend-only deploy must not silently ship against a 403ing backend.

    `gcloud run services describe` returns a URL for a service that EXISTS,
    whether or not anyone may invoke it -- existence and reachability are
    independent. So the frontend stage could bake that URL into VITE_WS_URL,
    publish, and report success over a backend rejecting every request: the exact
    symptom bd polyglot-pdf-pidtg's gate prevents, via the one path it did not
    cover (it sits in the BACKEND stage, and both channel wrappers run the
    frontend as a SEPARATE `deploy-all.sh --frontend` process).
    """
    body = DEPLOY_ALL.read_text(encoding="utf-8")
    # The frontend stage begins at its own banner; scope to it so a backend-stage
    # call cannot satisfy this.
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    assert "verify_service_publicly_reachable" in fe, (
        "the frontend stage never consults the reachability gate, so a "
        "frontend-only deploy can ship against an unreachable backend"
    )


def test_frontend_stage_warns_rather_than_aborting():
    """Severity differs from the backend stage, deliberately.

    The backend stage just CREATED the service, so an unreachable one is that
    run's own doing -> fatal. In the frontend stage the backend is pre-existing,
    possibly mid-fix by someone else or deliberately private, and refusing to
    ship a frontend over someone else's IAM state is the gate crying wolf.
    """
    body = DEPLOY_ALL.read_text(encoding="utf-8")
    fe = body.split("DEPLOYING FRONTEND TO FIREBASE HOSTING")[1]
    assert "VERIFY_FAIL_IS_FATAL=false verify_service_publicly_reachable" in fe, (
        "the frontend stage must call the gate in WARN mode "
        "(VERIFY_FAIL_IS_FATAL=false), not the default fatal mode"
    )


def test_the_gate_defaults_to_fatal():
    """Leniency must be opted INTO, never inherited by forgetting the flag."""
    query = _reachability_query_owner()
    assert '"${VERIFY_FAIL_IS_FATAL:-true}"' in query, (
        "the severity switch must DEFAULT to true (fatal); a default of false "
        "would silently downgrade the backend stage's abort to a warning"
    )


def _reachability_query_owner() -> str:
    return _gate_function(DEPLOY_ALL)


@pytest.mark.parametrize("rel", ["deploy-demo.sh", "deploy-staging.sh"])
def test_channel_wrapper_rejects_an_unknown_argument(rel):
    """A typo must not deploy NOTHING and report success (bd polyglot-pdf-7aez9).

    Both wrappers' arg parsers had no `*)` arm, so `--front-end` matched nothing,
    every DEPLOY_* stayed false, the script deployed nothing, printed its success
    banner and exited 0. The operator then believes they verified a change they
    never deployed -- on staging, precisely the false confidence that tier exists
    to remove. deploy-all.sh has always errored on an unknown argument; this
    brings the wrappers in line.
    """
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    parser = body.split("for arg in")[1].split("esac")[0]
    assert "*)" in parser, (
        f"{rel}'s argument parser has no catch-all arm, so an unrecognised "
        f"argument is silently ignored and the script 'succeeds' having "
        f"deployed nothing."
    )
    assert "Unknown argument" in parser and "exit 1" in parser, (
        f"{rel} must FAIL on an unknown argument, not merely note it"
    )
