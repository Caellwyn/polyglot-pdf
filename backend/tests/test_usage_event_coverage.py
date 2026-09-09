"""Every paid call site under backend/ is known and emits a usage event.

WHY THIS FILE EXISTS. Usage event v2 only produces a trustworthy cost total if
NOTHING bills silently. The failure mode is not a wrong number, it is a call
site nobody remembered to instrument: costs accrue on the Google invoice while
the dashboard shows a smaller total, and there is no error anywhere to notice.
The gap is invisible precisely because the un-instrumented path works fine.

So this test enumerates the paid call sites MECHANICALLY -- by walking the AST
of everything Cloud Run executes -- rather than trusting anyone to remember to
register a new one (scar #8: enumerate the set, then pin the SET). A new
generate_content / live.connect / synthesize_speech call anywhere under
backend/ fails this test on the day it is added.

SCOPE, derived by EXCLUSION like backend/tests/unit/test_deployed_iam_envelope.py:
everything under backend/ minus what the deployed service does not run, so a NEW
package is covered the day it appears rather than the day someone adds it to a
list. backend/scripts/ is out of scope -- the probe scripts there run under an
operator's own credentials against their own budget, deliberately (they exist to
spend money measuring things), and they are not part of the product's cost.

TWO LAYERS, because they fail differently:
  1. ENUMERATION -- the set of paid sites equals the pinned allowlist. Catches a
     new, unregistered paid call.
  2. EMIT PROOF -- each site actually reaches the usage emitter. Catches a
     registered site whose instrumentation was removed or never added.

Layer 2's plumbing landed across three beads. bd polyglot-pdf-wio6m ships the
emitter CONTRACT; the per-path ids are carried by polyglot-pdf-cjifh (live)
and polyglot-pdf-t86oz (text + TTS) -- both DONE, so every ALLOWED_SITES
entry now has emit_wired=True and none of the parametrized cases below is
xfail any more. The live site was never xfail here (it already reached the
emitter); what bd cjifh added was making that call's context ids real end to
end, proven in backend/tests/unit/test_usage_event_live_plumbing.py rather
than in this file's source-level check. The text and TTS sites' equivalent
real-call-path proof (SDK client mocked, ids/cost asserted per usage_kind)
lives in backend/tests/unit/test_usage_event_text_tts.py.
"""

import ast
import pathlib

import pytest


# ---------------------------------------------------------------------------
# Layer 1: enumerate every paid call site
# ---------------------------------------------------------------------------

# The three SDK calls that cost money. Attribute names, matched on the call's
# dotted receiver path so an unrelated `.connect()` (a socket, a DB handle) is
# not mistaken for a Live session.
#
#   generate_content  -> client.aio.models.generate_content  (per-token)
#   live.connect      -> client.aio.live.connect             (per-token, bidi)
#   synthesize_speech -> tts_client.synthesize_speech        (per-character)
_PAID_ATTRS = {"generate_content", "synthesize_speech"}
_PAID_DOTTED_SUFFIXES = ("live.connect",)

# Everything under backend/ that Cloud Run does NOT execute. Same exclusion set
# as the IAM envelope guard, for the same reason: listing what to INCLUDE means a
# new package is silently unscanned.
_NOT_DEPLOYED = {"tests", ".venv", "__pycache__", "docs", "logs", "scripts"}


def _repo_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "backend" / "routes").is_dir():
            return parent
    return p.parent.parent.parent  # backend/tests/<file> -> repo root


REPO_ROOT = _repo_root()


def _deployed_sources():
    """Every .py file under backend/ that the Cloud Run service can execute."""
    backend = REPO_ROOT / "backend"
    for f in sorted(backend.rglob("*.py")):
        rel = f.relative_to(REPO_ROOT)
        if any(part in _NOT_DEPLOYED for part in rel.parts):
            continue
        yield f, rel


def _dotted_name(node: ast.Attribute) -> str:
    """Reconstruct the dotted receiver path of an attribute call."""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _is_paid_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr in _PAID_ATTRS:
        return True
    dotted = _dotted_name(node.func)
    return any(dotted.endswith(suffix) for suffix in _PAID_DOTTED_SUFFIXES)


def find_paid_call_sites():
    """(file, line, dotted-call) for every paid SDK call the service can make."""
    sites = []
    for path, rel in _deployed_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_paid_call(node):
                sites.append((rel.as_posix(), node.lineno, _dotted_name(node.func)))
    return sites


# THE PINNED SET. Keyed by (file, dotted call) -- deliberately NOT by line
# number, which churns on every unrelated edit above it and would make this a
# maintenance tax rather than a guard.
#
# Each entry records which usage_kind that site bills as, and whether the emit
# is wired yet. Adding a paid call means adding it here, which is the moment to
# decide what it costs and who pays for it.
ALLOWED_SITES = {
    ("backend/adapters/live_ai_gemini.py", "self._client.aio.live.connect"): {
        "usage_kind": "live_voice",
        # The live adapter emits per-turn usage through log_gemini_api_response,
        # with the firm/employee/link/kit/channel/model context ids populated
        # end to end (bd polyglot-pdf-cjifh) -- see
        # backend/tests/unit/test_usage_event_live_plumbing.py for the
        # real-handshake + per-turn-emit proof this test's source-level
        # _emits_usage check cannot drive.
        "emit_wired": True,
    },
    ("backend/adapters/text_ai_gemini.py", "self._client.aio.models.generate_content"): {
        # One site serves secretary, validator and translation; the kind is
        # chosen per call by the caller (bd polyglot-pdf-t86oz): validate()
        # passes usage_kind="text_validator", ask() "text_secretary",
        # translate_labels/translate_items "text_translation" -- all through
        # _generate -> _log_usage -> log_text_ai_usage.
        "usage_kind": "text_secretary",
        "emit_wired": True,
    },
    ("backend/services/spellback_tts.py", "synthesize_speech"): {
        # One site serves spell-back, notice and intro (intro_tts and
        # notice_tts both call _synthesize_sync). bd polyglot-pdf-t86oz wires
        # it: each of the three callers (synthesize_spellback here,
        # synthesize_notice, synthesize_intro) calls the shared
        # _log_tts_usage_event with its own usage_kind after synthesis.
        "usage_kind": "tts_spellback",
        "emit_wired": True,
    },
}


def test_no_unregistered_paid_call_sites():
    """Every paid call under backend/ is in the allowlist.

    THE point of this file. A new generate_content / live.connect /
    synthesize_speech call that nobody registered means money leaving the
    account with no usage event behind it.
    """
    found = {(f, call) for f, _line, call in find_paid_call_sites()}
    unregistered = found - set(ALLOWED_SITES)
    assert not unregistered, (
        "Unregistered paid call site(s): " + str(sorted(unregistered)) + ". "
        "Every call that bills must be listed in ALLOWED_SITES with the "
        "usage_kind it bills as, and must emit a usage event."
    )


def test_allowlist_has_no_stale_entries():
    """No allowlist entry points at a call site that no longer exists.

    The other direction: a stale entry is a claim of coverage for code that was
    deleted or renamed, which quietly shrinks what layer 1 actually checks.
    """
    found = {(f, call) for f, _line, call in find_paid_call_sites()}
    stale = set(ALLOWED_SITES) - found
    assert not stale, (
        "ALLOWED_SITES entries match no call site: " + str(sorted(stale)) + ". "
        "Remove them, or fix the path/call name if the code moved."
    )


def test_enumeration_actually_finds_the_known_sites():
    """The walker finds real calls -- it is not vacuously passing on zero.

    Without this, a broken matcher (wrong attribute name, a scope bug that
    excluded everything) would make both tests above pass trivially, reporting
    perfect coverage of nothing. The three known adapters must show up.
    """
    files = {f for f, _line, _call in find_paid_call_sites()}
    for expected in (
        "backend/adapters/live_ai_gemini.py",
        "backend/adapters/text_ai_gemini.py",
        "backend/services/spellback_tts.py",
    ):
        assert expected in files, (
            f"the AST walk found no paid call in {expected}; the matcher is "
            "broken and the coverage guarantee is vacuous"
        )


def test_scope_excludes_probe_scripts():
    """backend/scripts/ probes are deliberately out of scope.

    Pins the exclusion so nobody 'fixes' the walk to include them and then
    silences the resulting failures by widening the allowlist -- which would put
    operator-budget probe calls into the product's cost accounting.
    """
    files = {f for f, _line, _call in find_paid_call_sites()}
    assert not any(f.startswith("backend/scripts/") for f in files)


@pytest.mark.parametrize("usage_kind", sorted(
    {entry["usage_kind"] for entry in ALLOWED_SITES.values()}
))
def test_allowlisted_usage_kinds_are_valid(usage_kind):
    """Every usage_kind named in the allowlist is a member of the closed set."""
    from typing import get_args

    from backend.utils.log_schemas import UsageKind

    assert usage_kind in get_args(UsageKind), (
        f"{usage_kind!r} is not a valid usage_kind; add it to the UsageKind "
        "Literal in backend/utils/log_schemas.py or fix the allowlist entry"
    )


# ---------------------------------------------------------------------------
# Layer 2: each site reaches the usage emitter
# ---------------------------------------------------------------------------

def _emits_usage(module_path: str) -> bool:
    """True if the module reaches a usage emitter (directly or via a helper).

    Source-level rather than a live mock: the three call sites sit behind
    async SDK clients, thread pools and a model-fallback loop, and a mock deep
    enough to drive them would test the mock. What must be true is that the
    module owning a paid call also carries the emit -- which is exactly what
    goes missing when someone adds a call path and forgets the telemetry.
    """
    src = (REPO_ROOT / module_path).read_text(encoding="utf-8")
    return any(name in src for name in (
        "log_gemini_api_response",
        "log_text_ai_usage",
        "log_tts_usage",
        "_emit_usage",
    ))


@pytest.mark.parametrize(
    "site",
    sorted(ALLOWED_SITES),
    ids=lambda s: f"{s[0].split('/')[-1]}::{s[1].split('.')[-1]}",
)
def test_paid_site_emits_a_usage_event(site, request):
    """Each allowlisted paid call site emits a usage event.

    Every ALLOWED_SITES entry now has emit_wired=True (beads
    polyglot-pdf-cjifh and polyglot-pdf-t86oz finished the live and
    text/TTS plumbing respectively), so this simply asserts the emit. A
    future site added with emit_wired=False would xfail(strict) here again --
    strict, so wiring it turns this RED and forces the marker's removal
    rather than letting a stale xfail hide a later regression.
    """
    module_path, _call = site
    if not ALLOWED_SITES[site]["emit_wired"]:
        request.node.add_marker(pytest.mark.xfail(
            strict=True,
            reason=(
                f"{module_path}: usage emit not yet wired for this site "
                "(see the ALLOWED_SITES entry for the tracking bead)"
            ),
        ))
    assert _emits_usage(module_path), (
        f"{module_path} makes a paid call but never reaches a usage emitter -- "
        "this path bills with no telemetry behind it"
    )
