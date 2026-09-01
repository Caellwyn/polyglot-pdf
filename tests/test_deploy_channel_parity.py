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
    """Top-level FOO="bar" assignments, for expanding $VAR references below."""
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)="([^"$]*)"', text, re.MULTILINE)
    }


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
        return re.sub(
            r"\$([A-Z_][A-Z0-9_]*)",
            lambda m: constants.get(m.group(1), m.group(0)),
            value,
        )

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
