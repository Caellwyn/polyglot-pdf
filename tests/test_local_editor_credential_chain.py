"""The local editor's credential must agree across all FOUR links (bd borq).

`scripts/run-schema-editor.sh` mints a per-run token and hands the SAME value
to two different consumers. That value then travels a four-link chain, and
every link is a separate FILE in a separate language:

    run-schema-editor.sh   mints  SCHEMA_AUTHOR_TOKEN
      -> exports the same value as VITE_EDITOR_TOKEN
        -> remoteKitStore.ts reads import.meta.env.VITE_EDITOR_TOKEN
          -> sends it as the X-Editor-Token header
            -> require_editor_role reads that header

WHY THIS NEEDS A TEST AND NOT JUST CARE. Breaking any link degrades local mode
SILENTLY and in the most misleading possible direction: the editor still
loads, the panel still renders, lint just returns nothing -- which reads to an
author as "no problems found" rather than "auth failed". There is no error
toast, no red state, nothing. A findings-free panel is indistinguishable from
a clean schema.

The original bug (bd borq) was this chain broken at BOTH ends at once: the
launcher set no token, so the backend 503'd, and the frontend sent none, so it
would have 401'd anyway. bd polyglot-pdf-cpiw (PR #522) fixed both. Nothing
pinned the agreement, so a rename on either side could reintroduce it.

These tests read the ACTUAL shipped files rather than a reimplementation.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run-schema-editor.sh"
STORE = ROOT / "schema-editor" / "src" / "utils" / "remoteKitStore.ts"
ROUTES = ROOT / "backend" / "routes" / "editor_kit_routes.py"

# The four link names. Each appears in at least two files that must agree.
BACKEND_ENV_VAR = "SCHEMA_AUTHOR_TOKEN"
FRONTEND_ENV_VAR = "VITE_EDITOR_TOKEN"
HEADER = "X-Editor-Token"


def _read(p: Path) -> str:
    assert p.exists(), f"{p} is missing -- the credential chain moved"
    return p.read_text(encoding="utf-8")


def _code_only(text: str) -> str:
    """Drop comment lines.

    A substring check over the WHOLE file matches prose as happily as code.
    Measured: renaming the live read to VITE_EDITOR_TOKEN_V2 left this suite
    green, because two doc comments in remoteKitStore.ts still spell the old
    name -- the guard was reading the narrative instead of the artifact, which
    is the exact failure it exists to catch.
    """
    out = []
    in_block = False
    for line in text.split(chr(10)):
        t = line.strip()
        if in_block:
            # Interior of a /* ... */ block. Tracked with STATE rather than by
            # a leading-"*" test: a block whose continuation lines do not start
            # with "*" is legal, and the leading-marker version let such a line
            # through (fresh-eyes round 1). remoteKitStore.ts happens to use
            # JSDoc style today, so this was latent -- but the whole job of
            # this helper is telling code from prose, and it should not depend
            # on which comment style a file happens to prefer.
            if "*/" in t:
                in_block = False
            continue
        if t.startswith("//"):
            continue
        if t.startswith("/*"):
            if "*/" not in t:
                in_block = True
            continue
        if t.startswith("*"):
            continue
        out.append(line)
    return chr(10).join(out)


def test_launcher_mints_a_token_when_the_operator_supplies_none():
    """The fix for the ORIGINAL bug: no ambient env must still yield a token.

    Without this the backend fail-closes with 503 'the editor surface is not
    configured', which is exactly the symptom bd borq reported.
    """
    sh = _read(LAUNCHER)
    # The mint is guarded so an operator-supplied token still wins.
    assert re.search(rf'if \[ -z "\${BACKEND_ENV_VAR}" \]', sh), (
        f"{LAUNCHER.name} no longer mints {BACKEND_ENV_VAR} when unset. With "
        f"neither editor token in the environment, require_editor_role "
        f"fail-closes 503 and every /api/editor call dies -- the original bug."
    )
    assert "token_urlsafe" in sh, (
        f"{LAUNCHER.name}'s token mint no longer uses a random source."
    )


def test_launcher_hands_the_SAME_value_to_both_sides():
    """The two-sided half. A token the backend accepts but the frontend never
    sends 401s just as dead as no token at all."""
    sh = _read(LAUNCHER)
    # Backend consumer: the env var is exported into the uvicorn subshell.
    assert re.search(rf'{BACKEND_ENV_VAR}="\${BACKEND_ENV_VAR}"', sh), (
        f"{LAUNCHER.name} no longer exports {BACKEND_ENV_VAR} to the backend."
    )
    # Frontend consumer: the SAME shell variable, not a second mint.
    assert re.search(rf'{FRONTEND_ENV_VAR}="\${BACKEND_ENV_VAR}"', sh), (
        f"{LAUNCHER.name} must set {FRONTEND_ENV_VAR} from ${BACKEND_ENV_VAR} "
        f"-- the SAME value. Two independently minted tokens would 401: the "
        f"editor loads, lint returns nothing, and a findings-free panel looks "
        f"like a clean schema rather than an auth failure."
    )


def test_the_frontend_reads_the_env_var_the_launcher_sets():
    """Link 3. A rename here is invisible to the shell script."""
    ts = _code_only(_read(STORE))
    # WORD-BOUNDED. A bare substring check is defeated by a SUFFIXED rename:
    # VITE_EDITOR_TOKEN is a prefix of VITE_EDITOR_TOKEN_V2, so `in` matches
    # the renamed symbol and the guard passes on a broken chain (measured --
    # this test was green against exactly that mutation before the boundary).
    pattern = re.compile(
        r"import\.meta\.env\." + re.escape(FRONTEND_ENV_VAR) + r"\b"
    )
    assert pattern.search(ts), (
        f"{STORE.name} no longer reads {FRONTEND_ENV_VAR}, which "
        f"{LAUNCHER.name} sets. Local mode would fall back to the prompt path "
        f"and every editor call would 401."
    )


def test_the_frontend_sends_the_header_the_backend_reads():
    """Link 4. Two files, two languages, one string."""
    ts = _code_only(_read(STORE))
    py = _read(ROUTES)
    assert f"'{HEADER}'" in ts or f'"{HEADER}"' in ts, (
        f"{STORE.name} no longer sends the {HEADER} header."
    )
    # PIN THE PARAMETER, NOT THE PROSE. FastAPI derives the wire header from
    # the parameter NAME (x_editor_token -> X-Editor-Token), so that identifier
    # is the contract; the docstrings that also spell "X-Editor-Token" are not.
    #
    # The first cut asserted `HEADER.lower() in py.lower()` over the RAW file
    # and was defeated by renaming the parameter while leaving the docstrings
    # alone -- measured: the real header became X-Auth-Token and all 6 tests
    # stayed green (fresh-eyes round 1). That is the SAME comment-vs-code hole
    # already fixed on the TypeScript side; I had applied the fix to one
    # language and not the other, while the docstring claimed both.
    param = HEADER.lower().replace("-", "_")          # x-editor-token -> x_editor_token
    assert re.search(rf"\b{re.escape(param)}\s*:", py), (
        f"{ROUTES.name} no longer declares a `{param}` Header() parameter. "
        f"FastAPI names the wire header from that identifier, so renaming it "
        f"changes the header the backend expects while {STORE.name} keeps "
        f"sending {HEADER} -- every editor call 401s, and local mode degrades "
        f"to a findings-free panel that looks like a clean schema."
    )


@pytest.mark.parametrize("name", [BACKEND_ENV_VAR, FRONTEND_ENV_VAR])
def test_both_env_var_names_appear_in_the_launcher(name):
    """Set-style guard: renaming EITHER variable must fail here, not silently
    in a running editor. Parametrized so the failure names which one moved."""
    assert name in _read(LAUNCHER), (
        f"{name} is gone from {LAUNCHER.name}. If it was renamed, update the "
        f"consumer too: {BACKEND_ENV_VAR} is read by backend config, "
        f"{FRONTEND_ENV_VAR} by {STORE.name}."
    )
