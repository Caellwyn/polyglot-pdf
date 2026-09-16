"""Staging must mirror the demo's backend config (bd polyglot-pdf-hvui4).

deploy-staging.sh has always stated the contract: "Backend env MIRRORS
deploy-demo.sh exactly. That is the whole point of a staging channel: a config
difference between the two would mean staging stops predicting demo behavior,
and the deploy-only bugs this environment exists to catch are precisely the
config-shaped ones."

It did not mirror it. The staging script was written from a pre-#693 copy of
the demo config, so it carried none of the LINK_* variables and staging could
not mint or open a client link at all -- the one feature the pilot depends on.
Nothing failed; the two files simply disagreed.

REWRITTEN as a LINE DIFF of deploy/channels/staging.env and
deploy/channels/demo.env (bd polyglot-pdf-1s3ko). The earlier version parsed
the two bash wrappers with regexes -- a shell-string parser that had to track
quoting, comment stripping, continuation lines and transitive variable
resolution, and that paid for a bug in each. The config is now DATA in two
files with identical shape, so the guard is a diff, which cannot be defeated
by rewriting the shell around it.

The comparison is over KEYS AND VALUES, not raw file lines: the two files
carry channel-specific PROSE (each names the other as the file to promote
from), and a byte diff would either fail on that or force the comments to be
identical, which would make them wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANNELS = REPO_ROOT / "deploy" / "channels"
STAGING = CHANNELS / "staging.env"
DEMO = CHANNELS / "demo.env"
ADMIN = CHANNELS / "admin.env"
DEPLOY_ALL = REPO_ROOT / "deploy-all.sh"
DEPLOY_STAGING = REPO_ROOT / "deploy-staging.sh"
DEPLOY_DEMO = REPO_ROOT / "deploy-demo.sh"

# Values that are SUPPOSED to differ per channel, with the reason. Anything
# else appearing on one side only, or with a different value, is drift.
CHANNEL_SPECIFIC = {
    # A minted link is a base URL plus /f#t=<token>, so each channel must point
    # at its OWN frontend -- staging pointing at the demo origin would mint
    # links that open the demo, silently testing the wrong deployment.
    "LINK_BASE_URL",
    # The channel's own name, minted into every token as aud and verified on
    # open (bd polyglot-pdf-3q9qn). Identical values would defeat the isolation
    # completely, so this MUST differ -- asserted below, not merely permitted.
    "LINK_CHANNEL",
    # bd polyglot-pdf-3l2vp: the deployed commit. deploy-all.sh computes it
    # (git rev-parse HEAD) and cloudbuild.yaml passes the _SHA substitution, so
    # neither channel file declares it today. Listed because a deployed commit
    # is by its nature never equal across two channels deployed at different
    # times, so a future channel file pinning one (e.g. holding staging on an
    # older verified SHA) must not be rejected as drift.
    "GIT_SHA",
    # Sprint 23 C2 (bd polyglot-pdf-bwevj): /ws/fill checks the browser Origin
    # against this list, and the voice app opens the socket from ITS channel's
    # Hosting site directly (no rewrite for WebSockets) -- so each channel
    # must name its own app site (demo: polyglot-demo-aa709; staging:
    # polyglot-app-staging) and must not name the other's. The shared editor
    # origins are in both. Pinned per channel by
    # backend/tests/unit/test_ws_first_frame_credential.py.
    "CORS_EXTRA_ORIGINS",
}

SECTIONS = ("SET_ENV_VARS", "SET_SECRETS", "SERVICE_ACCOUNT")


def parse_channel_file(path: Path) -> dict[str, dict[str, str]]:
    """The Python twin of deploy-all.sh's read_channel_section.

    Deliberately a SEPARATE implementation rather than a subprocess call into
    bash: the point of this guard is that the file is plain data, and a parser
    that shells out could only test the shell.
    """
    sections: dict[str, dict[str, str]] = {name: {} for name in SECTIONS}
    current: str | None = None
    for lineno, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            assert current in SECTIONS, (
                f"{path.name}:{lineno}: unknown section {current} -- the "
                f"parser and deploy-all.sh both know only {sorted(SECTIONS)}"
            )
            continue
        assert current is not None, (
            f"{path.name}:{lineno}: {line!r} appears before any section "
            "header, so deploy-all.sh's parser would silently drop it"
        )
        assert "=" in line, f"{path.name}:{lineno}: not KEY=value: {line!r}"
        key, _, value = line.partition("=")
        assert key, f"{path.name}:{lineno}: empty key"
        assert key not in sections[current], (
            f"{path.name}:{lineno}: {key} is declared twice in {current} -- "
            "gcloud takes the last one, so the first is silently dead"
        )
        sections[current][key] = value
    return sections


@pytest.fixture(scope="module")
def staging() -> dict[str, dict[str, str]]:
    return parse_channel_file(STAGING)


@pytest.fixture(scope="module")
def demo() -> dict[str, dict[str, str]]:
    return parse_channel_file(DEMO)


def test_both_channel_files_parse(staging, demo):
    """Guard the guard: a parser that finds nothing passes vacuously."""
    assert len(staging["SET_ENV_VARS"]) > 3
    assert len(demo["SET_ENV_VARS"]) > 3
    assert staging["SERVICE_ACCOUNT"].get("SERVICE_ACCOUNT")
    assert demo["SERVICE_ACCOUNT"].get("SERVICE_ACCOUNT")


@pytest.mark.parametrize("section", SECTIONS)
def test_staging_sets_every_key_the_demo_sets(staging, demo, section):
    """The mirror contract, in the direction that actually broke.

    Staging missing a demo key means the channel cannot exercise a feature the
    demo has, so it stops predicting demo behaviour for exactly that feature.
    """
    missing = sorted(set(demo[section]) - set(staging[section]))
    assert missing == [], (
        f"deploy/channels/staging.env {section} is missing {missing}, which "
        "demo.env sets. Staging must mirror the demo -- add them to STAGING "
        "first, verify on staging, then promote."
    )


@pytest.mark.parametrize("section", SECTIONS)
def test_staging_adds_no_key_the_demo_lacks(staging, demo, section):
    """Drift in the other direction is equally a divergence.

    A staging-only setting means staging tests something the demo never runs.
    """
    extra = sorted(set(staging[section]) - set(demo[section]))
    assert extra == [], (
        f"deploy/channels/staging.env {section} sets {extra}, which demo.env "
        "does not. Either promote it to the demo or remove it."
    )


@pytest.mark.parametrize("section", SECTIONS)
def test_shared_keys_have_identical_values(staging, demo, section):
    """Same key, same value -- except where the channel MUST differ."""
    differing = {
        key: (staging[section][key], demo[section][key])
        for key in set(staging[section]) & set(demo[section])
        if staging[section][key] != demo[section][key]
        and key not in CHANNEL_SPECIFIC
    }
    assert differing == {}, (
        f"{section} differs between the channels: {differing}. If a "
        "difference is deliberate, add the key to CHANNEL_SPECIFIC with the "
        "reason -- do not let it drift silently."
    )


def test_each_channel_declares_its_own_link_channel(staging, demo):
    """The isolation claim's whole basis: the two names must differ.

    CHANNEL_SPECIFIC exempts LINK_CHANNEL from the equality check, so without
    this the two could carry the SAME value and nothing would notice -- and a
    shared channel name means every token's aud matches both backends. An
    exemption without an assertion is a hole.
    """
    s = staging["SET_ENV_VARS"]["LINK_CHANNEL"]
    d = demo["SET_ENV_VARS"]["LINK_CHANNEL"]
    assert s != d, (
        f"both channels declare LINK_CHANNEL={s!r}; every link would open on "
        "either backend, which is the bug this claim exists to fix"
    )
    # Pinned to the literal names because the redemption collection derives
    # from them: link_redemptions for the demo, link_redemptions_<channel>
    # elsewhere. Renaming a channel silently orphans its ledger.
    assert d == "demo", f"demo.env declares LINK_CHANNEL={d!r}"
    assert s == "staging", f"staging.env declares LINK_CHANNEL={s!r}"


def test_link_base_url_points_at_each_channels_own_site(staging, demo):
    """The one deliberate difference, asserted rather than merely allowed."""
    s = staging["SET_ENV_VARS"]["LINK_BASE_URL"]
    d = demo["SET_ENV_VARS"]["LINK_BASE_URL"]
    assert s != d, (
        "both channels mint links against the same origin; staging would be "
        "testing the demo deployment"
    )
    assert "staging" in s, f"staging's LINK_BASE_URL ({s}) does not name staging"
    assert "staging" not in d, f"the demo's LINK_BASE_URL ({d}) is a staging origin"


def test_both_channels_bind_the_same_secrets(staging, demo):
    """--set-secrets REPLACES the whole secret block.

    So a channel that lists a partial set silently drops the rest. Keeping the
    two lists identical is what makes promoting staging to demo safe.
    """
    assert staging["SET_SECRETS"] == demo["SET_SECRETS"]


def test_the_link_signing_key_is_actually_bound(staging):
    """Without it the mint route 503s, which is bd hvui4's whole point."""
    assert "LINK_TOKEN_SECRET" in staging["SET_SECRETS"]


def test_both_channels_declare_an_explicit_runtime_service_account(staging, demo):
    """SERVICE_ACCOUNT became explicit and versioned in bd polyglot-pdf-1s3ko.

    It used to be an inline SA_EMAIL constant in each wrapper. An absent
    --service-account leaves the revision on the Compute default SA, which
    lacks roles/aiplatform.user -- so the Vertex path fails at runtime with a
    deploy that exited 0.
    """
    for name, parsed in (("staging", staging), ("demo", demo)):
        sa = parsed["SERVICE_ACCOUNT"].get("SERVICE_ACCOUNT", "")
        assert sa.endswith(".iam.gserviceaccount.com"), (
            f"{name}.env SERVICE_ACCOUNT is {sa!r}, not a service account"
        )
        assert sa.startswith("polyglot-backend-sa@"), (
            f"{name}.env runs as {sa!r}; the public backend's runtime identity "
            "is polyglot-backend-sa (CLAUDE.md scar 7 -- it deliberately "
            "lacks firebaseauth.users.get)"
        )


def test_the_admin_file_is_not_in_the_parity_pair():
    """admin.env is deliberately different, and must stay parseable.

    There is ONE admin service backing BOTH channels' data, so it has no
    channel of its own: a different runtime identity and a different ASGI
    entrypoint. Parsing it here means a format mistake in the file the
    admin-service target reads fails in THIS suite rather than in a build.
    """
    admin = parse_channel_file(ADMIN)
    assert admin["SET_ENV_VARS"]["APP_MODULE"] == "admin_backend.main:app"
    sa = admin["SERVICE_ACCOUNT"]["SERVICE_ACCOUNT"]
    assert sa.startswith("admin-backend-sa@"), (
        f"admin.env runs as {sa!r}; the admin service must NOT share the "
        "public backend's identity -- it reads and writes firm, credit and "
        "audit data the voice backend must never reach"
    )


# ---------------------------------------------------------------------------
# THE WIRING: the channel file must actually reach gcloud.
#
# A data file nothing reads is the same defect this bead's ancestor fixed: a
# value that looks configured and never reaches the service. The wrappers used
# to build BACKEND_ENV inline; that is now forbidden, and each link in the new
# chain gets its own assertion.
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    """The executable part of a shell line.

    Splitting on the first hash truncates a line whose hash is inside quotes,
    so track quoting. A false NEGATIVE (claiming a live line is absent) would
    silently disable a guard.
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


def _live_lines(script: Path) -> list[str]:
    return [
        _strip_comment(line)
        for line in script.read_text(encoding="utf-8").splitlines()
    ]


def _live_text(script: Path) -> str:
    return "\n".join(_live_lines(script))


def test_deploy_all_no_longer_defines_the_env_block_inline():
    """THE POINT OF THE BEAD: the channel env must come from the FILE.

    deploy-all.sh may still assemble the COMPUTED keys (GOOGLE_CLOUD_PROJECT,
    the FORM_KITS_* trio, GIT_SHA, APP_MODULE) -- none of those is static data.
    What it must NOT do is spell out channel settings, because a Cloud Build
    step cannot read a bash string, and a restated config is exactly the drift
    this file exists to catch.

    DERIVED from the shipped channel file rather than a hand-typed list: a
    restated list is the same bug one level up, and it goes stale the moment
    someone adds a setting.
    """
    text = _live_text(DEPLOY_ALL)
    for key in sorted(parse_channel_file(STAGING)["SET_ENV_VARS"]):
        assert f"{key}=" not in text, (
            f"deploy-all.sh still sets {key} inline. Channel settings belong "
            "in deploy/channels/<channel>.env, which cloudbuild.yaml reads too."
        )


def test_deploy_all_reads_the_channel_file():
    """The parser must exist and be called for the backend stage."""
    lines = _live_lines(DEPLOY_ALL)
    assert any("read_channel_section() {" in line for line in lines), (
        "deploy-all.sh defines no read_channel_section parser"
    )
    joined = "\n".join(lines)
    assert "deploy/channels/$DEPLOY_CHANNEL.env" in joined, (
        "deploy-all.sh never composes the channel file path, so DEPLOY_CHANNEL "
        "selects nothing"
    )
    for section in SECTIONS:
        assert section in joined, (
            f"deploy-all.sh never reads the {section} section, so that half "
            "of every channel file is silently ignored"
        )


@pytest.mark.parametrize(
    "script,channel",
    [(DEPLOY_STAGING, "staging"), (DEPLOY_DEMO, "demo")],
    ids=["staging", "demo"],
)
def test_each_wrapper_names_its_channel_in_the_invocation(script: Path, channel: str):
    """Containment is not position.

    A DEPLOY_CHANNEL assignment that has lost its trailing backslash is a
    standalone assignment the child process never sees -- the exact
    containment-vs-proximity defeat this file's ancestor paid two rounds for.
    So walk BACKWARD from the deploy-all.sh call over its continuation lines
    and require the assignment to be IN the env prefix.
    """
    lines = [line.rstrip() for line in _live_lines(script)]
    call = next(
        (i for i, line in enumerate(lines) if "./deploy-all.sh" in line), None
    )
    assert call is not None, f"could not locate {script.name}'s deploy-all.sh call"

    prefix: list[str] = []
    i = call - 1
    while i >= 0 and lines[i].endswith("\\"):
        prefix.append(lines[i].rstrip("\\").strip())
        i -= 1
    # The assignment may be the FIRST word of the call line itself.
    prefix.append(lines[call].strip())

    needle = 'DEPLOY_CHANNEL="' + channel + '"'
    assert any(needle in line for line in prefix), (
        f"{script.name} does not pass DEPLOY_CHANNEL={channel} as part of its "
        f"deploy-all.sh invocation (env prefix is {prefix}) -- the channel "
        "file is never read and the service deploys with bare defaults"
    )


@pytest.mark.parametrize(
    "script", [DEPLOY_STAGING, DEPLOY_DEMO], ids=["staging", "demo"]
)
def test_no_wrapper_rebuilds_the_channel_env_inline(script: Path):
    """The wrappers must not carry a second copy of the settings.

    BACKEND_EXTRA_ENV survives for deploy-time-only values (deploy-admin.sh's
    ADMIN_SERVICE_URL). It must no longer carry channel configuration.
    """
    text = _live_text(script)
    for key in sorted(parse_channel_file(STAGING)["SET_ENV_VARS"]):
        assert f"{key}=" not in text, (
            f"{script.name} still sets {key} inline -- it belongs in "
            "deploy/channels/<channel>.env, the one source Cloud Build reads."
        )


def _gcloud_run_deploy_argv(text: str) -> list[str]:
    """The ARGUMENT lines of the gcloud run deploy invocation.

    Follows backslash continuations and stops at the first line that does not
    continue. An earlier version sliced to the next blank line, overran by ~14
    lines, and let a reviewer disable a flag while leaving its literal in a
    trailing comment -- passing 12/12 with the flag gone.
    """
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "gcloud run deploy" in line)
    argv: list[str] = []
    i = start
    while i < len(lines):
        code = lines[i].split("#", 1)[0].rstrip()
        if code.strip():
            argv.append(code.strip())
        continued = code.endswith("\\")
        i += 1
        if not continued:
            break
    return argv


def test_deploy_all_passes_env_secrets_and_sa_to_gcloud():
    """Building the values and never expanding them is the classic defeat."""
    argv = _gcloud_run_deploy_argv(DEPLOY_ALL.read_text(encoding="utf-8"))
    assert len(argv) > 5, f"could not parse the gcloud invocation (got {argv})"
    assert any('--set-env-vars="$BACKEND_ENV"' in arg for arg in argv), (
        f"BACKEND_ENV never reaches gcloud. Parsed argv: {argv}"
    )
    assert any('"${SECRETS_FLAG[@]}"' in arg for arg in argv), (
        f"SECRETS_FLAG is built but never passed. Parsed argv: {argv}"
    )
    assert any('"${SA_FLAG[@]}"' in arg for arg in argv), (
        f"SA_FLAG is built but never passed. Parsed argv: {argv}"
    )


def test_deploy_all_layers_the_channel_sections_into_those_flags():
    """Each section must be wired to ITS flag, not merely read.

    Reading the secrets section into a variable nothing forwards is the
    "documented but never passed" bug (bd polyglot-pdf-hvui4) one level up.
    """
    text = _live_text(DEPLOY_ALL)
    assert 'BACKEND_ENV="$BACKEND_ENV,$CHANNEL_ENV"' in text, (
        "deploy-all.sh reads SET_ENV_VARS but never appends it to BACKEND_ENV"
    )
    assert '[ -z "$BACKEND_SECRETS" ] && BACKEND_SECRETS="$CHANNEL_SECRETS"' in text, (
        "deploy-all.sh reads SET_SECRETS but never feeds BACKEND_SECRETS, so "
        "--set-secrets binds nothing for a channel that relies on the file"
    )
    assert (
        '[ -z "$BACKEND_SERVICE_ACCOUNT" ] && BACKEND_SERVICE_ACCOUNT="$CHANNEL_SA"'
        in text
    ), (
        "deploy-all.sh reads SERVICE_ACCOUNT but never feeds "
        "BACKEND_SERVICE_ACCOUNT, so the revision runs as the Compute default"
    )


def test_an_empty_channel_env_section_is_refused():
    """--set-env-vars REPLACES the block, so an empty file must not deploy.

    Without this branch a channel file that lost its SET_ENV_VARS entries
    would deploy the bare computed defaults -- every LINK_*, VERTEXAI and CORS
    setting silently gone, with the deploy exiting 0.
    """
    text = _live_text(DEPLOY_ALL)
    assert 'if [ -z "$CHANNEL_ENV" ]; then' in text, (
        "deploy-all.sh does not refuse an empty SET_ENV_VARS section"
    )


# ---------------------------------------------------------------------------
# THE PROVISIONING the wiring depends on.
#
# Carried over unchanged from the pre-rewrite version of this file. The rewrite
# replaced the bash-regex parsing of the WRAPPERS with a diff of the channel
# FILES, which retired the wrapper parsers -- but this guard never depended on
# them, and the dependency it protects (SECRETS_FLAG in deploy-all.sh, still
# live) is untouched by that change. Dropping it would leave a project rebuilt
# from setup-gcp-project.sh unable to deploy, failing only at deploy time.
# ---------------------------------------------------------------------------

SETUP_GCP = REPO_ROOT / "scripts" / "setup-gcp-project.sh"


def _has_live_line(script: Path, token: str) -> bool:
    """Is `token` on a line the shell actually EXECUTES?

    A whole-file substring check passes when the pinned line is commented out
    and the token survives in the comment -- the containment-vs-proximity
    defeat this file documents for the gcloud argv, applied to provisioning.
    """
    return any(token in line for line in _live_lines(script))


def _api_enabling_scripts_that_bind_secrets() -> list[Path]:
    """Every shell script that enables APIs AND can reach a --set-secrets deploy.

    DISCOVERED rather than listed: a hard-coded pair cannot notice a third
    provider, and "a list that must be complete but is restated by hand" is the
    exact bug this file exists to catch.

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
    deploy_all_text = DEPLOY_ALL.read_text(encoding="utf-8")

    if "SECRETS_FLAG" not in deploy_all_text:
        pytest.skip("no --set-secrets wiring, so the role is not required")

    assert _has_live_line(SETUP_GCP, "roles/secretmanager.secretAccessor"), (
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
    # set" bug this file exists to catch, and a fourth provider added later
    # would pass silently. Any script that BOTH enables APIs and can reach a
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
            "add-iam-policy-binding is not API-gated, so the grant succeeds "
            "and the deploy fails later."
        )
