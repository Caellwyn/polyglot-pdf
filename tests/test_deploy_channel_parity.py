"""Staging must mirror the demo's backend config (bd polyglot-pdf-hvui4).

deploy-staging.sh states the contract itself: "Backend env MIRRORS
deploy-demo.sh exactly. That is the whole point of a staging channel: a config
difference between the two would mean staging stops predicting demo behavior,
and the deploy-only bugs this environment exists to catch are precisely the
config-shaped ones."

It did not mirror it. The staging script was written from a pre-#693 copy of
the demo config, so it carried none of the LINK_* variables and staging could
not mint or open a client link at all -- the one feature the pilot depends on.
Nothing failed; the two files simply disagreed, and only a human diffing them
side by side would notice.

DERIVED FROM THE SCRIPTS, never a hard-coded list. A test that restates the
expected variables is the same bug one level up: it goes stale the moment
someone adds a setting, which is exactly how the drift happened.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO = REPO_ROOT / "deploy-demo.sh"
STAGING = REPO_ROOT / "deploy-staging.sh"

# Values that are SUPPOSED to differ per channel, with the reason. Anything
# else appearing on one side only is drift.
CHANNEL_SPECIFIC = {
    # A minted link is `<base>/f#t=<token>`, so each channel must point at its
    # OWN frontend -- staging pointing at the demo origin would mint links that
    # open the demo, silently testing the wrong deployment.
    "LINK_BASE_URL",
}


def _shell_constants(text: str) -> dict[str, str]:
    """Top-level FOO="bar" assignments, resolved transitively.

    An earlier version excluded any value containing `$`, which silently
    dropped every DERIVED constant (GCP_PROJECT, FIREBASE_PROJECT, SA_EMAIL...)
    -- so `expand()` fell back to the literal "$NAME" and two channels writing
    the SAME unresolved token compared equal while resolving to different
    origins at deploy time. A guard that cannot resolve a value must not
    silently treat it as comparable.
    """
    raw = {
        m.group(1): m.group(2)
        for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)="([^"]*)"', text, re.MULTILINE)
    }

    # Resolve nested references. Bounded iteration, not recursion: a cycle
    # leaves the token unresolved, which _expand then reports rather than
    # silently comparing.
    for _ in range(5):
        changed = False
        for name, value in list(raw.items()):
            new = re.sub(
                r"\$\{?([A-Z_][A-Z0-9_]*)\}?",
                lambda m: raw.get(m.group(1), m.group(0)),
                value,
            )
            if new != value:
                raw[name] = new
                changed = True
        if not changed:
            break
    return raw


def _backend_extra_env(script: Path) -> dict[str, str]:
    """Parse the BACKEND_EXTRA_ENV assignment into a name -> value map.

    Values are shell-EXPANDED against the script's own constants: staging
    writes `LINK_BASE_URL=https://$STAGING_SITE.web.app`, and comparing the
    literal `$STAGING_SITE` would test the spelling rather than the origin.
    """
    text = script.read_text(encoding="utf-8")
    match = re.search(r'BACKEND_EXTRA_ENV="([^"]*)"', text)
    assert match, f"no BACKEND_EXTRA_ENV assignment found in {script.name}"

    constants = _shell_constants(text)

    def expand(value: str) -> str:
        expanded = re.sub(
            r"\$\{?([A-Z_][A-Z0-9_]*)\}?",
            lambda m: constants.get(m.group(1), m.group(0)),
            value,
        )
        # An UNRESOLVED token must not be compared as if it were a value: two
        # channels both writing "$GCP_PROJECT" would compare equal while
        # resolving to different origins. Fail loudly instead.
        assert "$" not in expanded, (
            f"{script.name}: could not resolve {value!r} (got {expanded!r}). "
            "Add the constant to the script or teach _shell_constants about it "
            "-- comparing an unresolved token would pass for the wrong reason."
        )
        return expanded

    pairs: dict[str, str] = {}
    for chunk in match.group(1).split(","):
        if "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        pairs[name.strip()] = expand(value.strip())
    return pairs


def _secrets(script: Path) -> str:
    text = script.read_text(encoding="utf-8")
    match = re.search(r'BACKEND_SECRETS_COMMON="([^"]*)"', text)
    assert match, f"no BACKEND_SECRETS_COMMON assignment found in {script.name}"
    return match.group(1)


@pytest.fixture(scope="module")
def demo_env() -> dict[str, str]:
    return _backend_extra_env(DEMO)


@pytest.fixture(scope="module")
def staging_env() -> dict[str, str]:
    return _backend_extra_env(STAGING)


def test_both_scripts_parse(demo_env, staging_env):
    """Guard the guard: an extractor that finds nothing passes vacuously."""
    assert len(demo_env) > 3
    assert len(staging_env) > 3


def test_staging_sets_every_variable_the_demo_sets(demo_env, staging_env):
    """The mirror contract, in the direction that actually broke.

    Staging missing a demo variable is the drift that shipped: it means the
    channel cannot exercise a feature the demo has, so it stops predicting demo
    behaviour for exactly that feature.
    """
    missing = sorted(set(demo_env) - set(staging_env))
    assert missing == [], (
        f"deploy-staging.sh is missing {missing}, which deploy-demo.sh sets. "
        "Staging must mirror the demo's backend env -- add them there FIRST, "
        "verify on staging, then promote."
    )


def test_staging_adds_no_variable_the_demo_lacks(demo_env, staging_env):
    """Drift in the other direction is equally a divergence.

    A staging-only setting means staging is testing something the demo will
    never run.
    """
    extra = sorted(set(staging_env) - set(demo_env))
    assert extra == [], (
        f"deploy-staging.sh sets {extra}, which deploy-demo.sh does not. "
        "Either promote it to the demo or remove it."
    )


def test_shared_variables_have_identical_values(demo_env, staging_env):
    """Same name, same value -- except where the channel MUST differ."""
    differing = {
        name: (demo_env[name], staging_env[name])
        for name in set(demo_env) & set(staging_env)
        if demo_env[name] != staging_env[name] and name not in CHANNEL_SPECIFIC
    }
    assert differing == {}, (
        f"these settings differ between the channels: {differing}. If a "
        "difference is deliberate, add the name to CHANNEL_SPECIFIC with the "
        "reason -- do not let it drift silently."
    )


def test_link_base_url_points_at_each_channels_own_site():
    """The one deliberate difference, asserted rather than merely allowed.

    CHANNEL_SPECIFIC exempts LINK_BASE_URL from the equality check, so without
    this the two could point at the SAME origin and nothing would notice --
    which is the failure that matters (staging minting links that open the
    demo).
    """
    demo = _backend_extra_env(DEMO)["LINK_BASE_URL"]
    staging = _backend_extra_env(STAGING)["LINK_BASE_URL"]

    assert demo != staging, (
        "both channels mint links against the same origin; staging would be "
        "testing the demo deployment"
    )
    assert "staging" in staging, (
        f"staging's LINK_BASE_URL ({staging}) does not name the staging site"
    )
    assert "staging" not in demo, (
        f"the demo's LINK_BASE_URL ({demo}) points at a staging origin"
    )


def test_both_channels_bind_the_same_secrets():
    """--set-secrets REPLACES the whole secret block.

    So a channel that lists a partial set silently drops the rest. Keeping the
    two lists identical is what makes promoting staging -> demo safe.
    """
    assert _secrets(DEMO) == _secrets(STAGING)


def test_the_link_signing_key_is_actually_bound():
    """Without it the mint route 503s, which is the whole point of this bead."""
    assert "LINK_TOKEN_SECRET" in _secrets(STAGING)


# ---------------------------------------------------------------------------
# THE WIRING, not just the values.
#
# The first version of this file asserted only that the two string CONSTANTS
# existed and matched. A reviewer deleted the entire fix -- first the
# `BACKEND_SECRETS=` hand-off in deploy-staging.sh, then `"${SECRETS_FLAG[@]}"`
# from the gcloud invocation itself, reproducing the exact hvui4 bug where
# --set-secrets never reaches gcloud on ANY channel -- and the suite passed
# 7/7 both times.
#
# A constant nothing forwards is the same defect this bead exists to fix: a
# value that looks configured and never reaches the service. So each link in
# the chain gets its own assertion.
# ---------------------------------------------------------------------------

DEPLOY_ALL = REPO_ROOT / "deploy-all.sh"


def _strip_comment(line: str) -> str:
    """The executable part of a shell line.

    Splitting on the first '#' truncates a line whose '#' is inside quotes --
    e.g. deploy-all.sh's `echo "...   # expect 200"`. No line these guards
    inspect looks like that today, but a false NEGATIVE (claiming a live line
    is absent) would silently disable a guard, so track quoting.
    """
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


def _live_text(script: Path) -> str:
    """The script with comments removed -- what the shell actually runs."""
    return "\n".join(
        _strip_comment(l) for l in script.read_text(encoding="utf-8").splitlines()
    )


def _has_live_line(script: Path, token: str) -> bool:
    """Is `token` on a line the shell actually EXECUTES?

    A whole-file substring check passes when the pinned line is commented out
    and the token survives in the comment -- the containment-vs-proximity
    defeat this file already documents for the gcloud argv, which I then
    repeated in the provisioning guards below.
    """
    return any(token in _strip_comment(l)
               for l in script.read_text(encoding="utf-8").splitlines())


def _api_enabling_scripts_that_bind_secrets() -> list[Path]:
    """Every shell script that enables APIs AND can reach a --set-secrets deploy.

    DISCOVERED rather than listed: a hard-coded pair cannot notice a third
    provider, and "a list that must be complete but is restated by hand" is the
    exact bug this bead exists to fix.

    A script qualifies when it both runs `gcloud services enable` and is on the
    secret-binding path -- either it passes --set-secrets itself, or it hands
    BACKEND_SECRETS to the engine that does. backend/deploy-new.sh enables APIs
    but does neither (independent legacy bootstrap), so it is correctly out.
    """
    found: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*.sh")):
        # Exclude RELATIVE to the repo root: this repo is often checked out
        # inside a `.claude/worktrees/...` path, so testing the absolute parts
        # for ".claude" filtered out every file and the discovery silently
        # returned nothing. The `>= 2` floor below is what caught it.
        rel_parts = path.relative_to(REPO_ROOT).parts
        if "node_modules" in rel_parts or ".claude" in rel_parts:
            continue
        # LIVE lines only, like the assertions themselves: a script that merely
        # MENTIONS BACKEND_SECRETS in prose would otherwise be required to
        # enable an API it never uses -- a false positive that would send the
        # next author chasing a non-dependency.
        text = _live_text(path)
        if "gcloud services enable" not in text:
            continue
        binds = "--set-secrets" in text or "BACKEND_SECRETS" in text
        # The engine itself binds; a bootstrap that provisions FOR it counts
        # too, since its whole job is making that deploy possible.
        provisions = "secretmanager.secretAccessor" in text
        if binds or provisions:
            found.append(path)
    return found


@pytest.mark.parametrize("script", [DEMO, STAGING], ids=["demo", "staging"])
def test_channel_forwards_its_secrets_to_deploy_all(script: Path):
    """The channel must PASS the constant, not merely define it."""
    text = script.read_text(encoding="utf-8")
    assert _has_live_line(script, 'BACKEND_SECRETS="$BACKEND_SECRETS_COMMON"'), (
        f"{script.name} defines BACKEND_SECRETS_COMMON but never hands it to "
        "deploy-all.sh, so the secret silently never binds"
    )


def test_deploy_all_builds_the_flag_from_backend_secrets():
    """deploy-all.sh must turn BACKEND_SECRETS into --set-secrets."""
    text = DEPLOY_ALL.read_text(encoding="utf-8")
    assert _has_live_line(DEPLOY_ALL, 'SECRETS_FLAG=(--set-secrets "$BACKEND_SECRETS")')


def _gcloud_run_deploy_argv(text: str) -> list[str]:
    """The ARGUMENT lines of the gcloud run deploy invocation, comments removed.

    Follows backslash continuations from the command line and stops at the
    first line that does not continue -- which is what "the invocation" means.

    An earlier version sliced to the next blank line. That overran by ~14 lines
    (the line after the last argument is four spaces, not empty), so a reviewer
    disabled the flag and left the literal in a trailing COMMENT: gcloud never
    saw --set-secrets, bash -n parsed clean, and the suite passed 12/12. Being
    NEAR the invocation is not being IN it -- the same containment-vs-proximity
    error this repo has paid for before.
    """
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if "gcloud run deploy" in l)

    argv: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        # A comment line is not an argument, even mid-continuation.
        code = line.split("#", 1)[0].rstrip()
        if code.strip():
            argv.append(code.strip())
        continued = code.endswith("\\")
        i += 1
        if not continued:
            break
    return argv


def test_deploy_all_passes_the_flag_to_gcloud():
    """...and must actually include it in the gcloud argv.

    This is the assertion whose absence let a reviewer delete the fix with the
    suite green: building the array and never expanding it is exactly the
    "documented but never passed" bug this bead is named for.
    """
    argv = _gcloud_run_deploy_argv(DEPLOY_ALL.read_text(encoding="utf-8"))

    # Guard the guard: an extractor that finds nothing passes vacuously.
    assert len(argv) > 5, f"could not parse the gcloud invocation (got {argv})"

    assert any('"${SECRETS_FLAG[@]}"' in arg for arg in argv), (
        "SECRETS_FLAG is built but never passed to gcloud run deploy -- the "
        "secret would silently never bind, which is bd polyglot-pdf-hvui4 "
        f"reintroduced. Parsed argv: {argv}"
    )

    # The SA flag rides the same mechanism; if it vanished from argv the
    # parser has drifted rather than the script.
    assert any('"${SA_FLAG[@]}"' in arg for arg in argv)


def test_setup_grants_the_role_that_set_secrets_requires():
    """The provisioning script must grant what the deploy path depends on.

    Cloud Run refuses a revision whose runtime SA cannot read a bound secret,
    so passing --set-secrets creates a hard dependency on
    roles/secretmanager.secretAccessor. The live SA already had it, granted out
    of band -- but a project rebuilt from setup-gcp-project.sh alone would not,
    and the failure lands at deploy time on a script someone runs unattended.

    Tied to the SECRETS_FLAG wiring deliberately: if a later change removes the
    flag this can go too, and if the flag stays the role must.
    """
    setup = REPO_ROOT / "scripts" / "setup-gcp-project.sh"
    deploy_all_text = DEPLOY_ALL.read_text(encoding="utf-8")

    if "SECRETS_FLAG" not in deploy_all_text:
        pytest.skip("no --set-secrets wiring, so the role is not required")

    assert _has_live_line(setup, "roles/secretmanager.secretAccessor"), (
        "deploy-all.sh binds secrets via --set-secrets, but "
        "setup-gcp-project.sh does not grant secretmanager.secretAccessor on a "
        "LIVE line -- a project built from that script cannot deploy"
    )

    # AND the API, in EVERY list that claims to guarantee the APIs.
    #
    # Three rounds on one dependency: (1) the flag without the role, (2) the
    # role without the API -- add-iam-policy-binding is not API-gated, so the
    # script exits 0 and the deploy fails later -- and (3) the API in the
    # one-time bootstrap but not in deploy-all.sh's own list, which is the one
    # that runs on EVERY deploy and self-heals.
    #
    # DISCOVERED, not hard-coded: a hand-listed pair is the same "restate the
    # set" bug this bead exists to fix, and a fourth provider added later would
    # pass silently. Any script that BOTH enables APIs and can reach a
    # secret-binding deploy must carry it.
    providers = _api_enabling_scripts_that_bind_secrets()
    assert len(providers) >= 2, (
        f"expected to discover at least the bootstrap and deploy paths, got "
        f"{[p.name for p in providers]} -- the discovery has drifted"
    )

    for script in providers:
        assert _has_live_line(script, "secretmanager.googleapis.com"), (
            f"{script.name} enables APIs and can reach a --set-secrets deploy, "
            "but does not enable secretmanager.googleapis.com on a LIVE line. "
            "add-iam-policy-binding succeeds regardless, so the script reports "
            "success and the deploy fails."
        )


def test_no_secrets_means_no_flag():
    """A channel that sets nothing must not change the invocation.

    deploy-production.sh and a bare deploy-all.sh run pass no BACKEND_SECRETS;
    an unconditional --set-secrets would send gcloud an empty value and wipe
    every binding on the service.
    """
    text = DEPLOY_ALL.read_text(encoding="utf-8")
    assert _has_live_line(DEPLOY_ALL, "SECRETS_FLAG=()"), (
        "the array must default EMPTY so a channel with no secrets produces "
        "the same invocation as before this flag existed"
    )
