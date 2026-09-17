"""Deploy-channel isolation: staging must never deploy over the demo
(bd polyglot-pdf-9qn64).

WHY THIS EXISTS. The demo (polyglot-demo-aa709.web.app) is shown to investors
and pilot firms; staging (polyglot-app-staging.web.app) is the disposable test
deploy. They share ONE GCP/Firebase project, so the ONLY things keeping a
staging deploy off the demo are three pieces of wiring:

  1. cloudbuild.yaml mapping each CHANNEL to its own Cloud Run service,
  2. cloudbuild.yaml mapping each CHANNEL to its own Hosting target,
  3. each firebase.json hosting target rewriting /api/** to its OWN service.

Every one of those fails SILENTLY when broken: there is no runtime signal,
because the deploy genuinely succeeded -- at the wrong target.

WHERE THE WIRING MOVED (bd polyglot-pdf-oqtm7). Items 1 and 2 used to be about
deploy-all.sh honouring EXPORTED variables, because every deploy ran locally
and the channel travelled as a bash variable a bare assignment could silently
clobber -- which is exactly what shipped before bd polyglot-pdf-9qn64, and
what made deploy-production.sh's exported BACKEND_SERVICE_NAME a no-op for its
entire life. The deploy stages are Cloud Build steps now and the channel is a
trigger-fixed substitution, so there is no caller variable left to clobber;
what is pinned instead is the mapping itself, plus the refusal of an unknown
channel.

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
# 1. The BUILD must derive the service and the Hosting site from the channel.
#
# This used to be about deploy-all.sh honouring caller-exported variables:
# every deploy ran locally, and the channel travelled as an exported bash
# variable that a bare assignment could silently clobber. The deploy stages
# live in cloudbuild.yaml now (bd polyglot-pdf-oqtm7), where the channel is a
# TRIGGER-FIXED substitution -- there is no caller variable left to clobber,
# so what needs pinning is the mapping itself: each channel reaching its OWN
# service and its OWN Hosting target, and an unknown channel refusing rather
# than falling back to one of them.
# ---------------------------------------------------------------------------

CHANNEL_SERVICES = [("staging", STAGING_SERVICE), ("demo", DEMO_SERVICE)]
CHANNEL_HOSTING_TARGETS = [("staging", STAGING_TARGET), ("demo", DEMO_TARGET)]


def _channel_arms(var: str) -> list[tuple[str, str]]:
    """Every `<channel>) <VAR>="<value>" ;;` arm in the build, in file order.

    EVERY arm, not the first match: the channel-to-service mapping is spelled
    out in more than one step (the deploy and the reachability gate each
    resolve it), and a guard that stops at the first occurrence passes while a
    later arm sends a staging deploy to the demo's service -- verified: that
    exact mutation went green before this helper existed.
    """
    body = _read("cloudbuild.yaml")
    return re.findall(
        rf'^\s*(\w+)\)\s*{var}="([^"]+)" ;;$', body, flags=re.MULTILINE
    )


@pytest.mark.parametrize("channel,service", CHANNEL_SERVICES)
def test_the_build_maps_each_channel_to_its_own_backend_service(channel, service):
    arms = _channel_arms("SERVICE")
    assert arms, "cloudbuild.yaml assigns SERVICE from no channel arm at all"
    mine = [value for arm, value in arms if arm == channel]
    assert mine, (
        f"cloudbuild.yaml has no {channel} arm assigning SERVICE -- a "
        f"{channel} deploy has no service to land on"
    )
    assert all(value == service for value in mine), (
        f"a {channel} arm maps to {sorted(set(mine))} rather than {service} -- "
        f"a {channel} deploy would land on another channel's Cloud Run service"
    )


@pytest.mark.parametrize("channel,target", CHANNEL_HOSTING_TARGETS)
def test_the_build_maps_each_channel_to_its_own_hosting_target(channel, target):
    arms = _channel_arms("HOSTING_TARGET")
    assert arms, "cloudbuild.yaml assigns HOSTING_TARGET from no channel arm"
    mine = [value for arm, value in arms if arm == channel]
    assert mine, f"cloudbuild.yaml has no {channel} arm assigning HOSTING_TARGET"
    assert all(value == target for value in mine), (
        f"a {channel} arm maps to {sorted(set(mine))} rather than {target} -- "
        f"a {channel} build would publish to another channel's site"
    )


def test_an_unknown_channel_aborts_rather_than_defaulting():
    """A fallback arm is how a misconfigured trigger reaches the demo.

    Every channel-dispatch `case` in the build must end in an arm that ABORTS.
    Pinned as a set over every such case (CLAUDE.md scar #8): a new
    channel-dispatching step that silently defaults would otherwise only be
    found by a wrong deploy.
    """
    body = _read("cloudbuild.yaml")
    lines = body.splitlines()
    dispatches = [
        i for i, line in enumerate(lines) if 'case "${_CHANNEL}" in' in line
    ]
    assert dispatches, "no channel dispatch found in cloudbuild.yaml"
    for start in dispatches:
        end = next(
            i for i in range(start + 1, len(lines)) if lines[i].strip() == "esac"
        )
        arms = lines[start + 1:end]
        catch_all = [ln for ln in arms if ln.strip().startswith("*)")]
        assert catch_all, (
            f"the channel dispatch at line {start + 1} has no catch-all arm"
        )
        assert all("exit 1" in ln for ln in catch_all), (
            f"the channel dispatch at line {start + 1} does not abort on an "
            f"unknown channel: {catch_all}"
        )


# ---------------------------------------------------------------------------
# 2. deploy-staging.sh must select the staging channel, and only it.
# ---------------------------------------------------------------------------


def test_staging_script_runs_both_of_its_channels_targets():
    """Backend AND frontend, each the staging one.

    The frontend target matters as much as the backend one: the build resolves
    the LIVE Cloud Run URL for its channel's service and bakes it into the
    bundle as VITE_WS_URL, so running the demo's frontend target from here
    would build a staging site that talks to the DEMO backend.
    """
    body = _read("deploy-staging.sh")
    for target in ("backend-staging", "frontend-staging"):
        assert f'"{target}"' in body, (
            f"deploy-staging.sh never runs the {target} target"
        )


def test_staging_script_never_names_the_demo_target():
    """The demo's build targets must not appear in the staging wrapper."""
    body = _read("deploy-staging.sh")
    for bad in ("backend-demo", "frontend-demo"):
        assert bad not in body, f"deploy-staging.sh targets the DEMO via {bad!r}"


def test_staging_does_not_deploy_firestore_rules():
    """Rules are PROJECT-wide: deploying them from staging hits the demo."""
    body = _read("deploy-staging.sh")
    assert "firestore-rules" not in body, (
        "deploy-staging.sh must not run the firestore-rules target -- rules "
        "are project-wide, so a staging rules deploy applies to the live demo."
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


def test_the_build_fails_hard_when_the_backend_url_is_unresolvable():
    """WebSockets BYPASS the Hosting rewrite -- VITE_WS_URL is the only binding.

    Firebase Hosting does not proxy WS upgrades, so the voice client connects to
    Cloud Run DIRECTLY (docs/technical_guide.md "Gotchas"). The per-target
    /api/** rewrite therefore binds only plain HTTP; for the voice path the
    build-time VITE_WS_URL is the ONLY thing tying a frontend to its backend.

    Both of its fallbacks name a DEMO backend (.env.demo's committed literal and
    config.ts's PRODUCTION_WS_URL). So if `gcloud run services describe` fails,
    warning-and-continuing would build a STAGING frontend driving the LIVE DEMO
    backend -- real Gemini spend and real confirmation_events against the demo's
    service -- while looking successful. That fires on the FIRST staging deploy,
    when the service does not exist yet.

    The build ALWAYS knows its channel (the trigger fixes _CHANNEL), so unlike
    the local script this replaces there is no bare-run case to warn for: every
    unresolved backend URL aborts.
    """
    body = _read("cloudbuild.yaml")
    lines = body.splitlines()
    marker = 'if [ -z "$$BACKEND_URL" ]; then'
    start = next(
        (i for i, ln in enumerate(lines) if ln.strip() == marker), None
    )
    assert start is not None, (
        "cloudbuild.yaml's frontend target does not check whether the backend "
        "Cloud Run URL resolved"
    )
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "fi")
    branch = lines[start + 1:end]
    assert any(ln.strip() == "exit 1" for ln in branch), (
        "an unresolved backend Cloud Run URL must ABORT the build -- otherwise "
        "the staging frontend silently ships pointing at the DEMO backend: "
        + repr(branch)
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

# Words that mark the script dead. Checked in the LINE-LOCAL neighbourhood of
# each mention, never file-wide -- see the docstring below.
DEATH_MARKERS = (
    "dead",
    "DEAD",
    "refuses to run",
    "unreachable",
    "inactive",
    "no live prod",
)


@pytest.mark.parametrize("doc", DOCS_MENTIONING_DEAD_PROD)
def test_doc_does_not_present_dead_prod_as_runnable(doc):
    """EVERY mention must be marked dead in its OWN neighbourhood.

    THE DEFEATABLE-BLACKLIST TRAP this replaces (bd polyglot-pdf-yz244, found by
    the pre-PR review of bd polyglot-pdf-9qn64). The first version banned three
    LITERAL phrasings, then searched the WHOLE FILE for a death word as a
    catch-all. Both halves were weak:

      - a blacklist is one synonym from defeat: any new wording presenting the
        script as runnable simply was not on the list;
      - the file-wide fallback was satisfied PERMANENTLY by unrelated prose. In
        README.md an existing "Production site (inactive)" line hundreds of lines
        away met it, so the reviewer rewrote the death paragraph into "To deploy
        production, run ./deploy-production.sh" and every test stayed green.

    So this asserts a PROPERTY per mention rather than banning phrasings, and
    scopes the evidence to the mention's own line plus two either side. Repo scar
    tissue, near-verbatim: a checker that infers a claim from text must scope the
    evidence region to exactly the claim -- widen it and nearby prose becomes
    evidence.
    """
    body = _read(doc)
    if "deploy-production" not in body:
        return
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if "deploy-production" not in line:
            continue
        # A doc's `**Tracks:**` header is a FILE LIST, not prose offering a
        # deploy path -- naming the script there is how the freshness checker
        # knows to watch it. Demanding a death marker inside a filename list
        # would be a false positive, so skip it. (Caught on this test's first
        # run: config-deployment.md's Tracks line failed the stricter check.)
        #
        # The exemption REQUIRES THE LINE TO ACTUALLY BE A FILE LIST, not merely
        # to start with the marker. A bare startswith() was smugglable -- the
        # review showed "**Tracks:** Run ./deploy-production.sh to go live."
        # would be waved through, reintroducing exactly the evasion this test
        # replaced a blacklist to prevent. So every token after the marker must
        # look like a path, which prose never does.
        stripped = line.lstrip()
        if stripped.startswith("**Tracks:**"):
            # Every token must LOOK LIKE A PATH: contain a "/" or carry a file
            # extension, or be a known extensionless repo file. Ordinary prose
            # words ("Run", "to", "go") satisfy none of those, which is what
            # makes the exemption unsmugglable -- an earlier, looser version
            # accepted any word made of path CHARACTERS and so waved through
            # "**Tracks:** Run ./deploy-production.sh to go live."
            #
            # Dockerfile is the one extensionless name this repo's Tracks lines
            # actually use; dotfiles like .gcloudignore and .firebaserc match the
            # extension branch (leading dot, then a name). A bare directory
            # reference (e.g. "admin-console/") is likewise a legitimate Tracks
            # entry -- an entire tree, not one file -- so a trailing "/" with no
            # filename after it counts too, PROVIDED it is a real directory in
            # this repo: a regex alone would wave through prose like "and/" (a
            # short common word plus a slash), reintroducing exactly the
            # smuggling this per-token check exists to close. Checking the
            # filesystem is the only thing that rules that out.
            tokens = stripped[len("**Tracks:**") :].split()

            def _is_path(tok: str) -> bool:
                if tok == "Dockerfile":
                    return True
                if tok.endswith("/"):
                    return (REPO_ROOT / tok).is_dir()
                return bool(re.fullmatch(r"[\w.\-/]*[/.][\w\-]+", tok)) and (
                    "/" in tok or "." in tok
                )

            if tokens and all(_is_path(t) for t in tokens):
                continue
        window = "\n".join(lines[max(0, i - 2) : i + 3])
        assert any(m in window for m in DEATH_MARKERS), (
            f"{doc}:{i + 1} mentions deploy-production.sh with no death marker "
            f"within two lines either side, so it reads as a live deploy path. "
            f"It targets an unreachable project and exits 1.\n"
            f"  line: {line.strip()!r}\n"
            f"  expected one of: {DEATH_MARKERS}"
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
