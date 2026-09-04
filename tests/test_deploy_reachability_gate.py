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
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Only a REAL invocation counts, never a mention. The gate's own comment
        # block and its error text both name the flag, so the moment
        # deploy-editor.sh gained a copy of the gate (bd polyglot-pdf-dldwb) a
        # whole-file substring search declared it a public-deploy script -- a
        # false positive, since it deploys only Hosting. Evidence region scoped
        # to the claim: the flag must appear on a line that is neither a comment
        # nor the gate's own error text.
        #
        # NOT filtered on "echo": an earlier draft excluded any line containing
        # it, which is redundant (the two real mentions are a comment and a
        # _gate_error line) and would have let a genuine invocation escape --
        # `gcloud run deploy ... --allow-unauthenticated || { echo fail; }` is a
        # real public deploy. A filter wide enough to hide the false positive was
        # also wide enough to hide a true one.
        if any(
            "--allow-unauthenticated" in ln
            and not ln.strip().startswith("#")
            and "_gate_error" not in ln
            for ln in text.splitlines()
        ):
            found.add(rel)
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
    assert re.search(r"verify_service_publicly_reachable[^\n]*\\?\s*\n?[^\n]*\bwarn\b", fe), (
        'the frontend stage must call the gate in WARN mode (a trailing "warn" '
        "argument), not the default fatal mode"
    )


def test_the_gate_defaults_to_fatal():
    """Leniency must be opted INTO, never inherited by forgetting the flag."""
    query = _reachability_query_owner()
    assert 'severity="${4:-fatal}"' in query, (
        "severity must be a positional ARGUMENT defaulting to fatal. As an ENV "
        "VAR it could not tell a deliberate per-call opt-out from an ambient "
        "exported value, so an exported VERIFY_FAIL_IS_FATAL=false disarmed the "
        "BACKEND stage's abort -- the exact bug this gate exists to stop."
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


def _run_gate_warn_mode(tmp_path: Path):
    """Execute the gate with the "warn" severity argument and an empty policy."""
    driver = tmp_path / "driver.sh"
    driver.write_text(
        'gcloud() { echo ""; return 0; }\n'
        + _gate_function(DEPLOY_ALL)
        + '\nverify_service_publicly_reachable "svc" "r" "p" warn\n'
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


def test_warn_mode_actually_continues_and_says_WARNING(tmp_path):
    """EXECUTE warn mode, do not merely assert the flag is spelled right.

    The sibling tests for this feature check that the string
    a "warn" argument appears in the
    frontend stage -- necessary, but a text assertion would still pass if the
    branches INSIDE the function were swapped (banner text, or the early
    return 0). Scar #9: test the tests. This runs the real shell.
    """
    rc, out, err = _run_gate_warn_mode(tmp_path)
    assert rc == 0, "warn mode must not abort the deploy"
    assert "REACHED_END" in out, "execution must continue past the gate"
    assert "WARNING" in err, (
        "warn mode must say WARNING, not DEPLOY FAILED -- the banner is the "
        "operator's only cue that the deploy was not stopped"
    )
    assert "DEPLOY FAILED" not in err
    assert "add-iam-policy-binding" in err, "the remedy must still be named"


def test_fatal_mode_is_unchanged_by_the_severity_switch(tmp_path):
    """The DEFAULT path must still abort -- the switch must not leak leniency."""
    rc, out, err = _run_gate(tmp_path, [])
    assert rc == 1, "the default (backend stage) mode must still abort"
    assert "REACHED_END" not in out
    assert "DEPLOY FAILED" in err
    assert "WARNING" not in err


def test_ambient_env_cannot_disarm_the_fatal_default(tmp_path):
    """An exported VERIFY_FAIL_IS_FATAL=false must NOT downgrade the abort.

    THE ENV-VAR TRAP (bd polyglot-pdf-xx9kd, found by the pre-PR cross-surface
    review). Severity was first read from the environment, and an env var cannot
    distinguish "the frontend stage set this for one call" from "it was ambient
    in the operator's shell". So an exported VERIFY_FAIL_IS_FATAL=false silently
    turned the BACKEND stage's abort into a warning -- reproducing the exact bug
    the gate exists to stop, on the one path where an unreachable service is
    definitely this run's own doing.

    Severity is a positional argument now, so only a real call site can request
    leniency. This runs the gate with the old variable exported and asserts it
    still aborts.
    """
    driver = tmp_path / "driver.sh"
    driver.write_text(
        'gcloud() { echo ""; return 0; }\n'
        + _gate_function(DEPLOY_ALL)
        + '\nverify_service_publicly_reachable "svc" "r" "p"\n'
        + 'echo "REACHED_END"\n',
        encoding="utf-8",
        newline="\n",
    )
    env = dict(os.environ)
    env["VERIFY_FAIL_IS_FATAL"] = "false"
    proc = subprocess.run(
        [BASH, "driver.sh"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(tmp_path),
        env=env,
        timeout=60,
    )
    assert proc.returncode == 1, (
        "an ambient VERIFY_FAIL_IS_FATAL=false disarmed the fatal default -- "
        "severity must come from the call site, not the environment"
    )
    assert "REACHED_END" not in proc.stdout
    assert "DEPLOY FAILED" in proc.stderr


def test_the_backend_stage_call_takes_the_fatal_default():
    """Appending `warn` to the BACKEND call must not be silently possible.

    The frontend call is pinned as warn-mode; nothing pinned the other
    direction. Adding a 4th argument to the backend-stage call downgrades the
    abort that bd polyglot-pdf-pidtg exists to enforce -- on the one path where
    an unreachable service is definitely that run's own doing -- and the whole
    suite would stay green (found by the round-2 cross-surface review).

    The backend call is identified as the one NOT inside the frontend stage, so
    this keeps working if either stage moves.
    """
    body = DEPLOY_ALL.read_text(encoding="utf-8")
    head, _, frontend = body.partition("DEPLOYING FRONTEND TO FIREBASE HOSTING")
    # Join shell line-continuations (a backslash followed by a NEWLINE) so each
    # call and its arguments form ONE logical line. Written as an explicit
    # concatenation because a literal "\\n" here is the two-character sequence
    # backslash-n, which matches nothing -- the exact no-op that made the
    # sibling ordering guard useless one review round earlier.
    logical = head.replace("\\" + "\n", " ")
    backend_calls = [
        ln.strip()
        for ln in logical.splitlines()
        if "verify_service_publicly_reachable" in ln
        and not ln.strip().startswith("#")
        and "()" not in ln
    ]
    assert backend_calls, "the backend stage no longer calls the gate"
    for call in backend_calls:
        args = call.split()[1:]
        assert len(args) == 3, (
            f"the backend-stage call passes {len(args)} arguments; it must pass "
            f"exactly 3 (service, region, project) and take the FATAL default. "
            f"A 4th argument silently downgrades the abort. Found: {call!r}"
        )


def _severity_of(rel: str, call: str) -> str:
    """Classify a gate call's severity from its SOURCE TOKEN, not from output.

    Reading the probe's stdout was defeatable: the driver stubs only the
    variables the real scripts use, so ANY other variable in the severity
    position expands to empty and was classified "fatal". Routing severity
    through a variable --

        SEV=warn verify_service_publicly_reachable "$S" "$R" "$P" "$SEV"

    -- therefore flipped backend/deploy-new.sh to warn mode with the whole suite
    green (found by the round-4 cross-surface review, on the same script and the
    same test the round-3 review had just hardened).

    So the severity must be a LITERAL: either absent (fatal, the default) or the
    exact token `warn`. A `$` anywhere in that position is refused outright --
    an indirected severity is unreviewable by inspection, which is the whole
    problem.
    """
    args = call.split()[1:]
    # Strip a leading VAR=value environment prefix, which bash applies to the
    # command rather than passing as an argument.
    while args and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", args[0]):
        args = args[1:]
    if len(args) <= 3:
        return "fatal"
    token = args[3]
    assert "$" not in token, (
        f"{rel}: the gate call's severity is a variable expansion ({token!r}), "
        f"so its effective value cannot be read from the source. Pass the "
        f"literal `warn`, or omit the argument for the fatal default. "
        f"Call: {call!r}"
    )
    stripped = token.strip('"').strip("'")
    assert stripped in ("warn", "fatal"), (
        f"{rel}: unrecognised severity {token!r} -- only `warn` or an omitted "
        f"argument (fatal) are valid. A typo falls through to fatal at runtime, "
        f"but must not pass unnoticed here. Call: {call!r}"
    )
    return stripped


# ---------------------------------------------------------------------------
# The OTHER set: scripts that bake a resolved backend URL into a frontend build.
# ---------------------------------------------------------------------------
#
# GATED_DEPLOY_SCRIPTS above is derived from --allow-unauthenticated, i.e. "who
# DEPLOYS a public Cloud Run service". That is the right set for the abort-on-
# create gate, and it correctly excludes deploy-editor.sh, which deploys only
# Hosting.
#
# But it is the WRONG set for this failure: baking an unreachable backend's URL
# into a frontend. That set is "who calls `gcloud run services describe` and
# exports the result as VITE_*", and it has two members. bd polyglot-pdf-816te
# fixed one; deploy-editor.sh stayed exposed for a further PR precisely because
# the guard keyed on the other set (bd polyglot-pdf-dldwb).
#
# Two sets, two lists. Deriving both mechanically is what stops a third script
# slipping between them.
URL_BAKING_SCRIPTS = ["deploy-all.sh", "deploy-editor.sh"]

# How many of a script's gate calls must pass "warn", and how many take the fatal
# default. deploy-all.sh has TWO call sites and they DIFFER -- the backend stage
# just created the service (fatal) while the frontend stage binds a pre-existing
# one (warn) -- so a single expected severity per script cannot express it. That
# is what a first draft of this map got wrong: it asserted "warn" for every call
# in deploy-all.sh and reddened on the backend stage's correct fatal call.
#
# {script: (n_warn, n_fatal)}
URL_BAKING_SEVERITY = {
    "deploy-all.sh": (1, 1),
    "deploy-editor.sh": (1, 0),
}


@pytest.mark.parametrize("rel", URL_BAKING_SCRIPTS)
def test_url_baking_script_consults_the_reachability_gate(rel, tmp_path):
    """Resolving a URL proves existence, never reachability.

    `gcloud run services describe --format 'value(status.url)'` answers for a
    service nobody may invoke, so a build can be pinned to a backend that 403s
    every request while the deploy reports success. In the editor's case every
    API call -- kit list, draft save, publish, the editing lock -- goes through
    that URL, and the 403s present as an access-code failure, sending the
    operator to debug auth.
    """
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "services describe" in body, (
        f"{rel} no longer resolves a backend URL; remove it from "
        f"URL_BAKING_SCRIPTS."
    )
    # A CALL, not merely the definition. Carrying the function proves nothing --
    # the first version of this assertion matched the definition itself, so
    # deleting the editor's call left all 30 tests green. Join continuations
    # first (the calls span two lines) and require a line that INVOKES it: not
    # the `name() {` definition, not a comment, not a printed message.
    logical = body.replace("\\" + "\n", " ")
    calls = [
        ln.strip()
        for ln in logical.splitlines()
        if "verify_service_publicly_reachable" in ln
        and not ln.strip().startswith("#")
        and "()" not in ln
    ]
    assert calls, (
        f"{rel} bakes a resolved backend URL into a frontend build without "
        f"CALLING the reachability gate, so it can ship pinned to a backend "
        f"that 403s every request. (Defining the function is not enough.)"
    )
    # ...and the call must actually WORK. Presence proved too little TWICE: the
    # first assertion matched the definition, and this one then passed over a
    # call whose line continuation had been corrupted into a literal "\\n", so
    # bash bound svc="n" and severity=$PROJECT. The gate queried a nonexistent
    # service, the query failed, and the __QUERY_FAILED__ path warn-and-skipped
    # -- a gate that could never fire, with every test green.
    #
    # So EXECUTE each call site against a probe that reports its arguments. Only
    # running the shell can distinguish a working call from a well-spelled one.
    severities: list[str] = []
    for call in calls:
        driver = tmp_path / f"call_{abs(hash(call))}.sh"
        driver.write_text(
            "BACKEND_SERVICE_NAME=SVC; REGION=REG; PROJECT=PRJ\n"
            "POLYGLOT_PROJECT_NAME=PRJ; SERVICE_NAME=SVC\n"
            "verify_service_publicly_reachable() {\n"
            '  echo "ARGC=$# SVC=$1 REGION=$2 PROJECT=$3 SEVERITY=$4"\n'
            "}\n" + call + "\n",
            encoding="utf-8",
            newline="\n",
        )
        proc = subprocess.run(
            [BASH, driver.name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(tmp_path),
            timeout=60,
        )
        assert proc.returncode == 0, (
            f"{rel}: the gate call does not even parse/run: {proc.stderr!r}"
        )
        out = proc.stdout.strip()
        assert "ARGC=3" in out or "ARGC=4" in out, (
            f"{rel}: the gate call passes the wrong number of arguments -- a "
            f"corrupted line continuation shifts them all. Got: {out!r} from "
            f"{call!r}"
        )
        # SEVERITY, pinned per script. Dropping the trailing `warn` left every
        # test green while flipping the editor's gate from WARN to FATAL: with
        # severity="${4:-fatal}", a 3-arg call aborts, and under `set -e` that
        # blocks EVERY editor deploy over a pre-existing backend's IAM state --
        # the exact "gate crying wolf" outcome warn mode exists to prevent.
        # Checking that arguments merely BIND could not see it (found by the
        # outer cross-surface review).
        assert "SVC=SVC" in out and "REGION=REG" in out and "PROJECT=PRJ" in out, (
            f"{rel}: the gate call's arguments do not bind to the script's own "
            f"service/region/project variables. Got: {out!r} from {call!r}"
        )
        severities.append(_severity_of(rel, call))
        # ...and the call must be a BARE command. The sibling guard
        # test_gate_is_called_as_a_bare_command is parametrized on
        # GATED_DEPLOY_SCRIPTS, so deploy-editor.sh escapes it entirely; a
        # `| cat` here would run the gate in a subshell where its `exit` cannot
        # reach the script. Latent while severity is `warn`, live the moment it
        # is not.
        for swallower in ("|", "$(", "&&", "||", "&"):
            assert swallower not in call, (
                f"{rel}: the gate call contains {swallower!r}, which runs it in "
                f"a subshell or guards it. Found: {call!r}"
            )

    want_warn, want_fatal = URL_BAKING_SEVERITY[rel]
    got_warn = severities.count("warn")
    got_fatal = severities.count("fatal")
    assert (got_warn, got_fatal) == (want_warn, want_fatal), (
        f"{rel}: expected {want_warn} warn-mode and {want_fatal} fatal-mode gate "
        f"call(s), got {got_warn} and {got_fatal} ({severities}). Dropping a "
        f"trailing `warn` flips a stage to FATAL, which under `set -e` blocks "
        f"every deploy over a PRE-EXISTING backend's IAM state -- the exact "
        f"'gate crying wolf' outcome warn mode exists to prevent."
    )


def test_url_baking_set_is_complete():
    """Pins the SET, so a third such script cannot ship unchecked.

    Membership is derived, not typed: a script belongs if it asks Cloud Run for
    a service URL AND exports a VITE_* variable (i.e. bakes it into a frontend
    build). backend/deploy-new.sh resolves a URL but exports no VITE_*, so it is
    correctly absent -- it deploys a service, it does not build a frontend.
    """
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
        "the set of scripts baking a resolved backend URL into a frontend build "
        "changed.\n"
        f"  unlisted (gate them, then add them): "
        f"{sorted(found - set(URL_BAKING_SCRIPTS))}\n"
        f"  listed but no longer baking: "
        f"{sorted(set(URL_BAKING_SCRIPTS) - found)}"
    )


def test_gate_copies_are_identical_across_all_three_scripts():
    """deploy-editor.sh now carries the gate too -- all copies must match.

    test_gate_copies_are_identical pins deploy-all.sh against deploy-new.sh;
    this extends that to the third copy, so the editor's gate cannot drift into
    a subtly weaker check than the one the other two run.
    """
    editor = _gate_function(REPO_ROOT / "deploy-editor.sh")
    assert editor == _gate_function(DEPLOY_ALL) == _gate_function(DEPLOY_NEW), (
        "the reachability gate has drifted between its three copies"
    )


# Exact (n_warn, n_fatal) for each service-CREATING script, mirroring
# URL_BAKING_SEVERITY. An "at least one fatal" lower bound was not enough: with
# only that, adding a SECOND call site lets the real one be downgraded while a
# decoy keeps the assertion satisfied. The round-3 review demonstrated it with an
# opt-in-strict shape --
#
#     if [ "$STRICT" = "1" ]; then verify_... "$S" "$R" "$P"
#     else                          verify_... "$S" "$R" "$P" warn; fi
#
# -- which leaves the DEFAULT path warning while the suite stays green. Exact
# counts also make config-deployment.md's "the counts are pinned per script"
# literally true rather than true-of-today's-tree.
GATED_DEPLOY_SEVERITY = {
    "deploy-all.sh": (1, 1),        # frontend stage warns, backend stage aborts
    "backend/deploy-new.sh": (0, 1),  # only ever creates; always fatal
}


@pytest.mark.parametrize("rel", GATED_DEPLOY_SCRIPTS)
def test_service_creating_script_takes_the_fatal_default(rel, tmp_path):
    """Every script that CREATES a service must let the gate abort.

    test_the_backend_stage_call_takes_the_fatal_default pins deploy-all.sh's
    backend call; backend/deploy-new.sh had NO such pin, so appending `warn`
    there downgraded its abort with all 30 tests green (found by the round-2
    cross-surface review).

    That is the worst place to lose it: deploy-new.sh's entire job is standing up
    a NEW service, and the refused-binding bug fires ONLY on new services. It is
    the highest-value call site of the three and was the only unguarded one.

    Parametrized over GATED_DEPLOY_SCRIPTS -- the scripts that pass
    --allow-unauthenticated, i.e. exactly those that create a public service --
    so a fourth such script inherits the pin automatically.
    """
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    logical = body.replace("\\" + "\n", " ")
    calls = [
        ln.strip()
        for ln in logical.splitlines()
        if "verify_service_publicly_reachable" in ln
        and not ln.strip().startswith("#")
        and "()" not in ln
    ]
    assert calls, f"{rel} never calls the gate"

    # A service-CREATING script must have at least one fatal call: the one
    # guarding the service it just made. Execute each, as a text check cannot
    # tell a 3-arg call from a 4-arg one whose continuation is corrupted.
    severities: list[str] = []
    for call in calls:
        driver = tmp_path / f"sc_{abs(hash(call))}.sh"
        driver.write_text(
            "BACKEND_SERVICE_NAME=SVC; SERVICE_NAME=SVC; REGION=REG\n"
            "PROJECT=PRJ; POLYGLOT_PROJECT_NAME=PRJ\n"
            "verify_service_publicly_reachable() { echo \"SEVERITY=$4\"; }\n"
            + call
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        proc = subprocess.run(
            [BASH, driver.name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(tmp_path),
            timeout=60,
        )
        assert proc.returncode == 0, (
            f"{rel}: a gate call does not parse/run: {proc.stderr!r}"
        )
        assert "SEVERITY=" in proc.stdout, (
            f"{rel}: a gate call produced no severity output, so it cannot be "
            f"classified: {proc.stdout!r} from {call!r}"
        )
        severities.append(_severity_of(rel, call))

    want_warn, want_fatal = GATED_DEPLOY_SEVERITY[rel]
    got_warn = severities.count("warn")
    got_fatal = severities.count("fatal")
    assert (got_warn, got_fatal) == (want_warn, want_fatal), (
        f"{rel} creates a public Cloud Run service; expected {want_warn} "
        f"warn-mode and {want_fatal} fatal-mode gate call(s), got {got_warn} and "
        f"{got_fatal} ({severities}). An unreachable service this script just "
        f"CREATED must ABORT the deploy, not warn."
    )
