"""The local editor must actually AUTHENTICATE, by whatever carries it (bd borq).

There is no shared credential to agree on any more. Per-user sign-in
(bd polyglot-pdf-yswp3) removed the last link of the old four-link chain: the
browser sends a per-person Firebase ID token, and LOCAL dev does not sign in at
all -- the launcher runs the backend with VFF_DISABLE_AUTH and the sign-in gate
is hosted-only. So what has to hold locally is now:

    run-schema-editor.sh  exports VFF_DISABLE_AUTH=true
      -> passes it EXPLICITLY to the uvicorn invocation
        -> editor_auth._dev_bypass_allowed() honours it off a deployed instance
          -> and REFUSES it on one (K_SERVICE), so this cannot leak to prod

WHY THIS NEEDS A TEST AND NOT JUST CARE. Breaking any link degrades local mode
SILENTLY and in the most misleading possible direction: the editor still
loads, the panel still renders, lint just returns nothing -- which reads to an
author as "no problems found" rather than "auth failed". There is no error
toast, no red state, nothing. A findings-free panel is indistinguishable from
a clean schema.

The original bug (bd borq) was the old chain broken at BOTH ends at once: the
launcher set no token, so the backend 503'd, and the frontend sent none, so it
would have 401'd anyway. bd polyglot-pdf-cpiw (PR #522) fixed both. Nothing
pinned the agreement, so a rename on either side could reintroduce it.

THE SYMPTOM IS WHAT THIS FILE OWNS, NOT THE MECHANISM. The mechanism has now
moved twice -- shared secret (borq) -> per-user token + bypass locally
(hn0jq) -> no client credential at all in local mode (yswp3) -- while the thing
that must never happen is identical each time: a local editor that fails auth
SILENTLY and shows an empty findings panel that reads as a clean schema. So
these tests pin whatever currently carries local auth, and are expected to be
rewritten (not deleted) the next time it moves.

WHAT CARRIES IT TODAY: VFF_DISABLE_AUTH. The launcher exports it and passes it
explicitly to uvicorn; editor_auth refuses it outright on a deployed instance,
which is what makes relying on it safe. The old VITE_EDITOR_TOKEN /
X-Editor-Token links are GONE from the client -- asserting on them now would
pin a chain that no longer exists.

These tests read the ACTUAL shipped files rather than a reimplementation.

ASCII only.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run-schema-editor.sh"
STORE = ROOT / "schema-editor" / "src" / "utils" / "remoteKitStore.ts"

# What the local chain rests on today. The client sends no shared credential
# at all, so there is no frontend env var or wire header left to agree on.
BYPASS_ENV_VAR = "VFF_DISABLE_AUTH"
# The header the CLIENT must no longer send. Asserted ABSENT (below): its
# return would mean the retired shared-code path came back.
RETIRED_HEADER = "X-Editor-Token"
RETIRED_FRONTEND_ENV_VAR = "VITE_EDITOR_TOKEN"


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


def test_launcher_enables_the_dev_bypass_so_the_local_editor_authenticates():
    """The fix for the ORIGINAL bug, at the layer that now carries it.

    Per-user identity (bd polyglot-pdf-hn0jq) made the minted token unverifiable
    -- it reaches Firebase's verify_id_token and 401s. Without the bypass every
    /api/editor/* call fails, which is bd borq's symptom exactly: lint returns
    nothing and an empty findings panel reads as a clean schema.
    """
    sh = _read(LAUNCHER)
    assert "VFF_DISABLE_AUTH" in sh, (
        f"{LAUNCHER.name} no longer enables the local auth bypass. The token it "
        f"mints is NOT a verifiable credential, so every /api/editor call 401s "
        f"and the editor silently returns nothing -- the original bug."
    )
    # The uvicorn call uses an EXPLICIT env prefix list, so the variable must
    # appear there -- riding on `export` alone made a one-word deletion break
    # the whole local editor with this suite green.
    assert re.search(r'VFF_DISABLE_AUTH="\$VFF_DISABLE_AUTH"', sh), (
        f"{LAUNCHER.name} no longer passes VFF_DISABLE_AUTH to the uvicorn "
        f"invocation. Its env prefix list is explicit, so a variable that is "
        f"merely exported can silently fail to reach the backend."
    )
    # Defaulted, not forced: an operator who supplies a real setting keeps it.
    assert re.search(r'VFF_DISABLE_AUTH="\$\{VFF_DISABLE_AUTH:-true\}"', sh), (
        f"{LAUNCHER.name} must DEFAULT the bypass, not override an operator's "
        f"explicit value."
    )


def test_the_client_sends_NO_shared_credential_any_more():
    """The retired links must stay retired.

    Per-user sign-in (bd polyglot-pdf-yswp3) removed the build-baked token and
    the X-Editor-Token header from the client. Re-adding either would put a
    shared secret back into a bundle anyone can read -- the exact posture the
    editor-identity epic exists to end -- and would do it silently, since the
    server still accepts that header until bd polyglot-pdf-rhc2v removes it.

    Asserted over CODE, not prose: both names legitimately appear in comments
    explaining what was retired, and matching those would make this vacuous.
    """
    ts = _code_only(_read(STORE))
    assert RETIRED_FRONTEND_ENV_VAR not in ts, (
        f"{STORE.name} reads {RETIRED_FRONTEND_ENV_VAR} again. That bakes a "
        f"shared credential into the bundle in PLAINTEXT (standard Vite VITE_* "
        f"behaviour) -- anyone who can open the site can read it. Identity "
        f"comes from the signed-in person's Firebase ID token."
    )
    assert RETIRED_HEADER not in ts, (
        f"{STORE.name} sends the {RETIRED_HEADER} header again. The server "
        f"still accepts it (until bd polyglot-pdf-rhc2v), so this would NOT "
        f"fail loudly -- it would quietly restore the shared-secret path."
    )


def test_the_launcher_bakes_no_credential_into_the_local_bundle():
    """The launcher half of the same property.

    It used to hand the minted token to the browser as VITE_EDITOR_TOKEN. The
    local editor now needs no client credential -- the backend's bypass answers
    before any token check -- so re-adding one would be dead config that reads
    like a live credential to the next author.
    """
    sh = _read(LAUNCHER)
    assert RETIRED_FRONTEND_ENV_VAR not in sh, (
        f"{LAUNCHER.name} sets {RETIRED_FRONTEND_ENV_VAR} again. Nothing reads "
        f"it: the local editor authenticates via {BYPASS_ENV_VAR} on the "
        f"backend, and the sign-in gate is hosted-only."
    )


def test_the_bypass_is_refused_on_a_deployed_instance():
    """What makes leaning on the bypass SAFE, asked of the real function.

    The local chain now rests entirely on VFF_DISABLE_AUTH, so the guarantee
    that it cannot apply in production is load-bearing rather than incidental.
    K_SERVICE is Cloud Run's marker: present means deployed, and the bypass must
    refuse itself however the env is set.
    """
    import importlib

    from backend.services import editor_auth

    importlib.reload(editor_auth)
    saved = {k: os.environ.get(k) for k in (BYPASS_ENV_VAR, "K_SERVICE")}
    try:
        os.environ[BYPASS_ENV_VAR] = "true"
        os.environ.pop("K_SERVICE", None)
        assert editor_auth._dev_bypass_allowed() is True, (
            "the local bypass no longer engages off a deployed instance -- "
            "every /api/editor call would 401 and the editor would silently "
            "return nothing, which is bd borq's symptom exactly."
        )
        os.environ["K_SERVICE"] = "polyglot-backend"
        assert editor_auth._dev_bypass_allowed() is False, (
            "the local bypass is NOT refused on a deployed instance. The whole "
            "local chain rests on this being unreachable in production."
        )
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
