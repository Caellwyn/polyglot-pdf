"""Deploy-channel isolation: staging must never deploy over the demo
(bd polyglot-pdf-9qn64).

WHY THIS EXISTS. The demo (polyglot-demo-aa709.web.app) is shown to investors
and pilot firms; staging (polyglot-app-staging.web.app) is the disposable test
deploy. They share ONE GCP/Firebase project, so the ONLY things keeping a
staging deploy off the demo are three pieces of wiring:

  1. deploy-all.sh honouring an EXPORTED BACKEND_SERVICE_NAME,
  2. deploy-all.sh honouring an EXPORTED FRONTEND_HOSTING_TARGET,
  3. each firebase.json hosting target rewriting /api/** to its OWN service.

Every one of those fails SILENTLY when broken. A bare `X="literal"` assignment
in deploy-all.sh (which is exactly what shipped before this bead -- and which
made deploy-production.sh's exported BACKEND_SERVICE_NAME a no-op for its entire
life) clobbers the caller's value with no error, a clean shell exit, and a
successful-looking deploy that has just overwritten the live demo. There is no
runtime signal, because the deploy genuinely succeeded -- at the wrong target.

So this pins the SET of wiring that keeps the channels apart, per CLAUDE.md scar
tissue #8 (enumerate the set, then pin the set, not the instance).

NOT tested here: that a deploy actually works. That needs a real deploy.
"""
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

DEMO_SERVICE = "polyglot-backend"
STAGING_SERVICE = "polyglot-backend-staging"
DEMO_TARGET = "app"
STAGING_TARGET = "app-staging"
STAGING_SITE = "polyglot-app-staging"
DEAD_PROJECT = "polyglot-forms-919f2"


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. deploy-all.sh must not CLOBBER caller-exported channel wiring.
# ---------------------------------------------------------------------------

# The two variables that select which channel a deploy lands on. Both must be
# defaulted (${VAR:-default}), never bare-assigned, or the channel scripts'
# exports are silently discarded.
CHANNEL_VARS = ["BACKEND_SERVICE_NAME", "FRONTEND_HOSTING_TARGET"]


@pytest.mark.parametrize("var", CHANNEL_VARS)
def test_deploy_all_honours_exported_channel_var(var):
    """A bare assignment would silently point staging at the demo's target."""
    body = _read("deploy-all.sh")
    # Find every top-level assignment to this variable.
    assigns = re.findall(rf'^{var}=(.*)$', body, flags=re.MULTILINE)
    assert assigns, f"{var} is not assigned in deploy-all.sh at all"
    for rhs in assigns:
        assert rhs.startswith(f'"${{{var}:-'), (
            f"deploy-all.sh assigns {var}={rhs.strip()} -- a bare assignment "
            f"CLOBBERS the value deploy-staging.sh exports, so a staging "
            f"deploy would land on the DEMO. Use "
            f'{var}="${{{var}:-<default>}}" instead.'
        )


@pytest.mark.parametrize(
    "var,default",
    [("BACKEND_SERVICE_NAME", DEMO_SERVICE), ("FRONTEND_HOSTING_TARGET", DEMO_TARGET)],
)
def test_deploy_all_default_is_the_demo_channel(var, default):
    """An unset var must mean the demo -- never an accidental staging deploy."""
    body = _read("deploy-all.sh")
    assert f'{var}="${{{var}:-{default}}}"' in body, (
        f"deploy-all.sh's default for {var} must be {default!r} so a bare "
        f"./deploy-all.sh run keeps its historical (demo) behavior."
    )


def test_deploy_all_uses_the_hosting_target_variable():
    """`--only hosting:app` hardcoded would ship staging's build to the demo."""
    body = _read("deploy-all.sh")
    assert 'firebase deploy --only "hosting:$FRONTEND_HOSTING_TARGET"' in body, (
        "deploy-all.sh must deploy the PARAMETERIZED hosting target; a "
        "hardcoded hosting:app publishes a staging build to the demo site."
    )
    assert "--only hosting:app " not in body, (
        "a hardcoded --only hosting:app remains in deploy-all.sh"
    )


# ---------------------------------------------------------------------------
# 2. deploy-staging.sh must select the staging channel, and only it.
# ---------------------------------------------------------------------------


def test_staging_script_exports_staging_service_for_both_stages():
    """Backend AND frontend stages both need the staging service name.

    The frontend stage matters as much as the backend one: deploy-all.sh
    resolves the LIVE Cloud Run URL for BACKEND_SERVICE_NAME and bakes it into
    the build as VITE_WS_URL. Omitting it there would build a staging frontend
    that talks to the DEMO backend.
    """
    body = _read("deploy-staging.sh")
    assert body.count(f'BACKEND_SERVICE_NAME="$STAGING_SERVICE_NAME"') == 2, (
        "deploy-staging.sh must pass BACKEND_SERVICE_NAME to BOTH the backend "
        "and frontend deploy-all.sh invocations"
    )
    assert f'STAGING_SERVICE_NAME="{STAGING_SERVICE}"' in body
    assert f'STAGING_HOSTING_TARGET="{STAGING_TARGET}"' in body
    assert 'FRONTEND_HOSTING_TARGET="$STAGING_HOSTING_TARGET"' in body


def test_staging_script_never_names_the_demo_target():
    """The literal demo service/site must not appear as a deploy target."""
    body = _read("deploy-staging.sh")
    for bad in (
        'BACKEND_SERVICE_NAME="polyglot-backend"',
        'FRONTEND_HOSTING_TARGET="app"',
        "--only hosting:app ",
    ):
        assert bad not in body, f"deploy-staging.sh targets the DEMO via {bad!r}"


def test_staging_does_not_deploy_firestore_rules():
    """Rules are PROJECT-wide: deploying them from staging hits the demo."""
    body = _read("deploy-staging.sh")
    assert "firebase deploy --only firestore:rules" not in body, (
        "deploy-staging.sh must not deploy firestore.rules -- rules are "
        "project-wide, so a staging rules deploy applies to the live demo."
    )


def test_staging_bare_run_skips_form_kits():
    """The kits bucket is SHARED: a bare staging run must not publish kits."""
    body = _read("deploy-staging.sh")
    assert "DEPLOY_FORM_KITS=false" in body, (
        "deploy-staging.sh must default form-kits deployment OFF -- the bucket "
        "is shared with the demo, so publishing changes the DEMO's form list."
    )


# ---------------------------------------------------------------------------
# 3. firebase.json / .firebaserc: each target routes to its own backend.
# ---------------------------------------------------------------------------


def _hosting_targets():
    cfg = json.loads(_read("firebase.json"))
    return {h["target"]: h for h in cfg["hosting"]}


@pytest.mark.parametrize(
    "target,service",
    [(DEMO_TARGET, DEMO_SERVICE), (STAGING_TARGET, STAGING_SERVICE)],
)
def test_hosting_target_rewrites_to_its_own_service(target, service):
    """The /api/** rewrite is what binds a site to a backend."""
    targets = _hosting_targets()
    assert target in targets, f"firebase.json has no {target!r} hosting target"
    api = [
        rw for rw in targets[target]["rewrites"] if rw.get("source") == "/api/**"
    ]
    assert len(api) == 1, f"{target} must have exactly one /api/** rewrite"
    assert api[0]["run"]["serviceId"] == service, (
        f"hosting target {target!r} rewrites /api/** to "
        f"{api[0]['run']['serviceId']!r}, expected {service!r} -- the two "
        f"channels would share a backend."
    )


def test_staging_target_is_mapped_to_its_own_site():
    rc = json.loads(_read(".firebaserc"))
    hosting = rc["targets"]["polyglot-demo-aa709"]["hosting"]
    assert hosting.get(STAGING_TARGET) == [STAGING_SITE], (
        f"{STAGING_TARGET} must map to the {STAGING_SITE} site in .firebaserc"
    )
    # And it must NOT collide with the demo's site.
    assert hosting[DEMO_TARGET] != hosting[STAGING_TARGET], (
        "staging and demo hosting targets resolve to the SAME site"
    )


# ---------------------------------------------------------------------------
# 4. The dead prod channel must stay dead.
# ---------------------------------------------------------------------------


def test_dead_production_script_refuses_to_run():
    """It targets an unreachable project (bd polyglot-pdf-je6iy).

    Left runnable, it is the obvious wrong guess for "deploy the real one".
    """
    body = _read("deploy-production.sh")
    assert re.search(r"^exit 1$", body, flags=re.MULTILINE), (
        "deploy-production.sh must exit non-zero -- its target project "
        f"({DEAD_PROJECT}) is dead and unreachable."
    )
    # The refusal must come before any deploy work: no gcloud/firebase call may
    # be reachable above it.
    exit_at = body.index("\nexit 1")
    head = body[:exit_at]
    for cmd in ("gcloud ", "firebase ", "./deploy-all.sh"):
        # Comment lines are fine; an executable line is not.
        for line in head.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert cmd not in stripped, (
                f"deploy-production.sh runs {cmd!r} BEFORE refusing; it must "
                f"refuse first so no work reaches the dead project."
            )


# ---------------------------------------------------------------------------
# 5. The frontend build must not silently bind to the WRONG channel's backend.
# ---------------------------------------------------------------------------


def test_explicit_channel_fails_hard_when_backend_url_unresolvable():
    """WebSockets BYPASS the Hosting rewrite -- VITE_WS_URL is the only binding.

    Firebase Hosting does not proxy WS upgrades, so the voice client connects to
    Cloud Run DIRECTLY (docs/technical_guide.md "Gotchas"). The per-target
    /api/** rewrite therefore binds only plain HTTP; for the voice path the
    build-time VITE_WS_URL is the ONLY thing tying a frontend to its backend.

    Both of its fallbacks name a DEMO backend (.env.demo's committed literal and
    config.ts's PRODUCTION_WS_URL). So if `gcloud run services describe` fails
    for an explicitly-selected channel, warning-and-continuing would build a
    STAGING frontend driving the LIVE DEMO backend -- real Gemini spend and real
    confirmation_events against the demo's service -- while looking successful.
    That fires on the FIRST staging deploy, when the service does not exist yet.
    """
    body = _read("deploy-all.sh")
    assert 'BACKEND_SERVICE_NAME_EXPLICIT="${BACKEND_SERVICE_NAME:-}"' in body, (
        "deploy-all.sh must capture whether the caller explicitly selected a "
        "channel BEFORE defaulting BACKEND_SERVICE_NAME."
    )
    assert 'elif [ -n "$BACKEND_SERVICE_NAME_EXPLICIT" ]; then' in body, (
        "the frontend stage must branch on an EXPLICIT channel when the backend "
        "URL cannot be resolved"
    )
    # The explicit-channel branch must ABORT, not warn.
    explicit_branch = body.split('elif [ -n "$BACKEND_SERVICE_NAME_EXPLICIT" ]; then')[1]
    explicit_branch = explicit_branch.split("else")[0]
    assert "exit 1" in explicit_branch, (
        "an explicitly-selected channel whose Cloud Run URL cannot be resolved "
        "must ABORT the build -- otherwise the staging frontend silently ships "
        "pointing at the DEMO backend."
    )


def test_capture_precedes_defaulting():
    """Order matters: capture after defaulting would make EVERY run 'explicit'."""
    body = _read("deploy-all.sh")
    capture = body.index('BACKEND_SERVICE_NAME_EXPLICIT="${BACKEND_SERVICE_NAME:-}"')
    default = body.index('BACKEND_SERVICE_NAME="${BACKEND_SERVICE_NAME:-polyglot-backend}"')
    assert capture < default, (
        "BACKEND_SERVICE_NAME_EXPLICIT must be captured BEFORE the default is "
        "applied; otherwise a bare deploy-all.sh run looks explicit and would "
        "start failing hard, breaking its historical behavior."
    )


# ---------------------------------------------------------------------------
# 6. Docs must not present the dead prod channel as runnable.
# ---------------------------------------------------------------------------

# The COMPLETE set of non-journal docs mentioning deploy-production.sh. The
# outer cross-surface review found these one per finding (scar #8): four docs
# were updated and six were missed. Pinning the SET means the next omission
# fails CI instead of costing a review round. Journal entries and
# planning_documents are historical records and are excluded by design.
DOCS_MENTIONING_DEAD_PROD = [
    ".claude/prime-closeout-override.md",
    ".claude/skills/run-local/SKILL.md",
    "AGENTS.md",
    "CLAUDE.md",
    "DEPLOYMENT.md",
    "README.md",
    "docs/components/config-deployment.md",
    "docs/doctrine/promotion-tiers.md",
    "docs/technical_guide.md",
]

# Phrasings that present the script as a live deploy path. Each must be absent.
RUNNABLE_CLAIMS = [
    "`deploy-demo.sh` / `deploy-production.sh` wrappers",
    "`deploy-demo.sh` and\n> `deploy-production.sh` ship",
    "stays maintainer-directed",
]


@pytest.mark.parametrize("doc", DOCS_MENTIONING_DEAD_PROD)
def test_doc_does_not_present_dead_prod_as_runnable(doc):
    """Every mention must mark it dead, never offer it as a deploy path."""
    body = _read(doc)
    for claim in RUNNABLE_CLAIMS:
        assert claim not in body, (
            f"{doc} still presents deploy-production.sh as runnable via "
            f"{claim!r}; it targets an unreachable project and exits 1."
        )
    # Wherever it IS named, the death must be stated nearby.
    if "deploy-production" in body:
        assert re.search(r"dead|DEAD|refuses to run|unreachable|inactive", body), (
            f"{doc} names deploy-production.sh without saying it is dead"
        )


def test_dead_prod_doc_set_is_complete():
    """The enumerated set must match reality, or the parametrization lies.

    Pins the SET, not its members (scar #8): a NEW doc that starts mentioning
    deploy-production.sh must be added here, not silently escape the check.
    """
    found = set()
    for path in REPO_ROOT.rglob("*.md"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "node_modules" in rel or rel.startswith(
            ("docs/journal/", "planning_documents/")
        ):
            continue
        try:
            if "deploy-production" in path.read_text(encoding="utf-8"):
                found.add(rel)
        except (OSError, UnicodeDecodeError):
            continue
    assert found == set(DOCS_MENTIONING_DEAD_PROD), (
        "DOCS_MENTIONING_DEAD_PROD is out of date.\n"
        f"  unlisted (add them): {sorted(found - set(DOCS_MENTIONING_DEAD_PROD))}\n"
        f"  listed but clean (remove): {sorted(set(DOCS_MENTIONING_DEAD_PROD) - found)}"
    )


# ---------------------------------------------------------------------------
# 7. The reachability gate lives in tests/test_deploy_reachability_gate.py.
# ---------------------------------------------------------------------------
#
# It used to be pinned HERE by asserting on deploy-all.sh's text, because the
# gate was inline. bd polyglot-pdf-6oi9s extracted it into a
# verify_service_publicly_reachable() function so backend/deploy-new.sh could
# carry a byte-identical copy -- and a function can be EXECUTED, which a text
# assertion never could.
#
# tests/test_deploy_reachability_gate.py now runs the real shell against
# synthetic IAM policies and asserts the actual exit code, covering strictly
# more than the assertions removed from here: allUsers-on-invoker passes,
# allUsers-on-a-non-invoker-role aborts (the false PASS), a multi-binding policy
# still passes (the false FAIL), a lookalike role aborts, and an inconclusive
# IAM read warns instead of aborting. It also pins the COMPLETE SET of scripts
# that deploy publicly, so a third one cannot ship ungated.
#
# One assertion did NOT survive verbatim: the old suite asserted the query has
# no `2>&1`. That is a code-SHAPE assertion, and the behavior it protected (a
# gcloud stderr notice satisfying the check) is already impossible because
# `grep -qx` requires the whole line to be exactly "roles/run.invoker" -- a
# warning always carries surrounding text. Verified by mutation, not assumed.
# test_gcloud_stderr_cannot_satisfy_the_check pins that OUTCOME instead.
