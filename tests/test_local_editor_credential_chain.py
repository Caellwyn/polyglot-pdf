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
    """Link 4, asked of the FRAMEWORK rather than of the source text.

    Two files, two languages, one wire header. The TypeScript side is a string
    literal, so it must be read from source. The Python side is NOT -- FastAPI
    computes the real answer and will tell us, so ask it.

    THREE WRONG VERSIONS PRECEDED THIS, every one measured:
      1. `"x-editor-token" in py.lower()` over the raw file. The DOCSTRINGS
         satisfied it, so renaming the parameter changed the real header while
         the test stayed green. Asserted against prose; caught nothing.
      2. A word-bounded search for the parameter NAME. That rejected
         `Header(alias="X-Editor-Token")` on a renamed parameter -- a valid
         refactor whose wire header is unchanged (verified 200). A guard that
         reddens on correct code teaches the next author to bypass it.
      3. Name OR literal alias. Still rejected `Header(alias=_HDR)` where the
         alias comes from a constant -- also valid, also verified 200.

    Each failed for the same reason: it pattern-matched SOURCE TEXT for
    something the framework already knows. Walking the dependant graph is
    immune to all three, because it reports the header the app actually binds
    however it was spelled -- and a comment naming the old header cannot fool
    it, because comments are not in the graph.
    """
    ts = _code_only(_read(STORE))
    assert f"'{HEADER}'" in ts or f'"{HEADER}"' in ts, (
        f"{STORE.name} no longer sends the {HEADER} header."
    )

    # Scoped to require_editor_role's OWN dependant, not to the whole app
    # (fresh-eyes round 4). "Does ANY route bind X-Editor-Token?" is a weaker
    # question than this docstring claims: an unrelated future route declaring
    # the same header would satisfy it while THIS dependency was broken.
    # Unexploitable today -- require_editor_role is the only Header() in the
    # backend -- but the set would silently absorb a second one.
    from fastapi.dependencies.utils import get_dependant
    from backend.routes.editor_kit_routes import require_editor_role

    dependant = get_dependant(path="/", call=require_editor_role)
    declared = set()
    stack = [dependant]
    while stack:
        d = stack.pop()
        for param in getattr(d, "header_params", []):
            declared.add(str(param.alias).lower())
        stack.extend(getattr(d, "dependencies", []))

    assert HEADER.lower() in declared, (
        f"require_editor_role no longer declares a {HEADER} header parameter "
        f"(it declares: {sorted(declared) or 'none'}). FastAPI binds the wire "
        f"header from the parameter name or an explicit Header(alias=...); "
        f"neither now yields {HEADER}, so the backend expects a different "
        f"header than {STORE.name} sends. Every editor call 401s, and local "
        f"mode degrades to a findings-free panel that reads as a clean schema "
        f"rather than an auth failure."
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
