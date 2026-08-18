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
    """Drop whole-line comments so an assertion cannot match PROSE.

    WHY: a substring check over a whole file matches a doc comment as happily
    as a live statement. Measured -- renaming the live read to
    VITE_EDITOR_TOKEN_V2 left this suite green, because two JSDoc comments in
    remoteKitStore.ts still spell the old name. The guard was reading the
    narrative instead of the artifact, which is the exact failure it exists to
    catch.

    SCOPE, deliberately narrow: this handles WHOLE-LINE comments -- `//` lines,
    and `/* ... */` blocks whose delimiters sit on their own lines (JSDoc
    style, which is what the scanned files use). It is NOT a JS parser and
    three cases are known-unhandled:
      - `/* c */ realCode();`  the trailing code is dropped with the comment
      - an unterminated `/*`   swallows the rest of the file
      - `"*/"` in a string     reads as a block close
    Each would DROP text, so the only risk is a false FAILURE (an assertion
    not finding code that is really there) -- never a false pass hiding a
    broken chain. That asymmetry is why a narrow helper is acceptable here
    rather than a parser: this guard's job is refusing to be fooled by prose,
    and over-stripping cannot fool it.

    If a scanned file ever adopts inline block comments, prefer moving the
    assertion to a real parse over widening these heuristics.
    """
    out = []
    in_block = False
    for line in text.split(chr(10)):
        t = line.strip()
        if in_block:
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
    # PIN WHAT DETERMINES THE WIRE HEADER, which is EITHER of two spellings:
    #   x_editor_token: Annotated[..., Header()]                  (name-derived)
    #   x_whatever:     Annotated[..., Header(alias="X-Editor-Token")]  (explicit)
    # FastAPI accepts both and both send X-Editor-Token, so both must pass.
    #
    # Two failures, opposite directions, both measured (fresh-eyes rounds 1-2):
    #  1. The first cut matched "x-editor-token" anywhere in the RAW file, so
    #     the DOCSTRINGS satisfied it -- renaming the parameter changed the real
    #     header and the test stayed green. Assert against prose, catch nothing.
    #  2. The second cut pinned the parameter NAME only, so the alias refactor
    #     above -- which keeps the wire header identical, verified 200 -- turned
    #     it RED. A guard that fails on correct code teaches the next author to
    #     distrust it, which is worse than the hole it was closing.
    param = HEADER.lower().replace("-", "_")
    name_derived = re.search(rf"\b{re.escape(param)}\s*:", py)
    explicit_alias = re.search(
        rf'Header\(\s*alias\s*=\s*["\']{re.escape(HEADER)}', py, re.I
    )
    assert name_derived or explicit_alias, (
        f"{ROUTES.name} no longer derives the {HEADER} wire header. FastAPI "
        f"takes it from either the parameter NAME ({param}) or an explicit "
        f"Header(alias=...). Neither is present, so the backend now expects a "
        f"different header than {STORE.name} sends -- every editor call 401s, "
        f"and local mode degrades to a findings-free panel that reads as a "
        f"clean schema rather than an auth failure."
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
