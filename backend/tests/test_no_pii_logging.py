"""Static guard against PII/PHI leaking into logs (bd polyglot-pdf-hjo).

polyglot-pdf handles immigration-form data (A-numbers, names, addresses, DOB)
and the backend logs to stdout -> Cloud Run -> BigQuery. The standing policy
(docs/standards/hipaa-pii-policy.md) is: NEVER log field values, user-speech
transcripts, or message text -- only field IDs, types, counts, lengths, and
timestamps. INFO/WARNING logs are always emitted in production, so a single
`value=value` in a log call is a live PII leak.

This is a SOURCE-LEVEL grep guard (no backend import needed, so it runs in the
repo-level suite regardless of backend test-collection state). It scans the two
files that build the fill/voice payloads for the value/transcript-logging
patterns that were fixed in bd hjo, so a regression re-introduces a test failure
rather than a silent BigQuery leak.
"""

import pathlib
import re

import pytest

# Resolve the repo root by walking up to the dir that contains `backend/`
# (this test lives at backend/tests/ so the configured `testpaths = backend/tests`
# runs it -- a security regression guard must run in the canonical suite).
def _repo_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "backend" / "routes").is_dir():
            return parent
    # Fallback: backend/tests/<file> -> repo root is two levels up from backend/.
    return p.parent.parent.parent


REPO_ROOT = _repo_root()

# Files that handle raw field values / user-speech transcripts and log heavily.
GUARDED_FILES = [
    "backend/routes/pdf_fill_routes.py",
    "backend/adapters/live_ai_gemini.py",
    # on_tool_call receives Gemini's tool args, which include field VALUES; it
    # previously print()'d them whole (bd polyglot-pdf-oeq).
    "backend/services/callback_handler.py",
]

# Kwarg NAMES that must never carry a raw value/text in a log call. We flag the
# kwarg whenever it is assigned ANYTHING (any variable, slice, f-string, attr)
# EXCEPT a safe metadata wrapper -- so a regression under a new variable name
# (value=selected_value, message=text, message=queued_msg) is still caught. The
# earlier version keyed on the right-hand variable name (value=value) and so
# silently missed value=selected_value / message=text; fresh-eyes flagged that.
_SENSITIVE_KWARGS = (
    "value", "values", "selected_value", "selected_values", "target_value",
    "original_value", "message", "text", "text_preview", "transcript",
    "sample", "available_options", "system_instruction",
)
# Right-hand sides that ARE safe: a metadata wrapper (len/type/bool/...), a
# metadata-named var (*_length / *_count / *_type / *_id), OR a literal constant
# (a quoted string or a number) -- a constant can't carry runtime PII, so e.g.
# `message="Session closed"` is fine while `message=text` is not.
_SAFE_RHS = re.compile(
    r"""^\s*(
        len\( | type\( | bool\( |              # metadata wrappers
        [A-Za-z_]*_(?:length|count|type|id|ids)\b |  # metadata-named var
        ["'] |                                  # string literal
        \d |                                    # number literal
        True\b | False\b | None\b               # constant
    )""",
    re.VERBOSE,
)
# Match `kwarg = <rhs>` up to the next comma/paren/eol, for each sensitive kwarg.
LEAK_PATTERNS = [
    re.compile(r"\b" + re.escape(k) + r"\s*=\s*(?P<rhs>[^,)\n#]+)")
    for k in _SENSITIVE_KWARGS
]


def _is_leak(match) -> bool:
    """A sensitive kwarg is a leak unless its RHS is a safe metadata wrapper."""
    rhs = match.group("rhs")
    return not _SAFE_RHS.match(rhs)


_LOG_CALL_START = re.compile(r"(?:self\.)?_log\.(?:info|warning|error|debug|critical)\s*\(")


def _scan_leaks(text: str):
    """Return [(lineno, line)] for sensitive kwargs inside a `_log.*(...)` call.

    Tracks paren depth so MULTI-LINE log calls (kwargs on their own lines) are
    covered, while assignments OUTSIDE log calls (e.g. `value_str = str(value)`,
    `message = f"..."`) are not flagged. Comments are stripped before matching so
    redaction notes ("# never log value") don't false-positive.
    """
    offenders = []
    depth = 0  # open-paren depth of the current _log.* call, 0 = not in one
    for lineno, raw in enumerate(text.splitlines(), 1):
        code = raw.split("#", 1)[0]
        if depth == 0:
            m = _LOG_CALL_START.search(code)
            if not m:
                continue
            depth = 1  # entered a log call on this line
            code_after = code[m.end():]
        else:
            code_after = code
        # Scan the in-call portion for sensitive kwargs that aren't safe metadata.
        for pat in LEAK_PATTERNS:
            for mm in pat.finditer(code_after):
                if _is_leak(mm):
                    offenders.append((lineno, raw.strip()))
                    break
        # Update paren depth; when it returns to 0 the call has closed.
        depth += code_after.count("(") - code_after.count(")")
        if depth < 0:
            depth = 0
    return offenders


# Sensitive identifiers that must never be interpolated into a positional sink
# like print(). `_log.*(...)` kwargs are covered by _scan_leaks above; this is
# the OTHER class of leak (bd polyglot-pdf-oeq): a bare
# `print(f"Arguments: {arguments}")` dumps the whole tool-call args (= field
# values) to stdout -> Cloud Run logs. We flag a sensitive var interpolated into
# an f-string; safe-metadata names (tool_name, *_id, *_count, ...) are fine.
_SENSITIVE_IDENTS = (
    "arguments", "args", "value", "values", "selected_value", "selected_values",
    "target_value", "original_value", "message", "text", "transcript",
    "field_values", "current_values", "system_instruction", "payload",
)
# An f-string interpolation `{<sensitive>}` or `{<sensitive>[...]/.attr/(...)}` --
# a word boundary before the name avoids matching e.g. `field_values_count`.
_FSTRING_SENSITIVE = re.compile(
    r"\{[^{}]*\b(?:" + "|".join(re.escape(i) for i in _SENSITIVE_IDENTS) + r")\b[^{}]*\}"
)
_PRINT_CALL = re.compile(r"\bprint\s*\(")


def _scan_print_leaks(text: str):
    """Return [(lineno, line)] for print() calls interpolating a sensitive var.

    Only flags a print whose argument f-string interpolates one of
    _SENSITIVE_IDENTS. Comments are stripped first so a redaction note can't
    false-positive. A safe-metadata interpolation (`{tool_name}`, `{arg_count}`)
    does not match because those names aren't in _SENSITIVE_IDENTS.
    """
    offenders = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        code = raw.split("#", 1)[0]
        if _PRINT_CALL.search(code) and _FSTRING_SENSITIVE.search(code):
            offenders.append((lineno, raw.strip()))
    return offenders


@pytest.mark.parametrize("rel", GUARDED_FILES)
def test_no_value_or_transcript_in_logs(rel):
    path = REPO_ROOT / rel
    assert path.exists(), f"guarded file missing: {rel}"
    text = path.read_text(encoding="utf-8")
    offenders = _scan_leaks(text) + _scan_print_leaks(text)
    assert not offenders, (
        "PII/PHI logging leak re-introduced (bd hjo / oeq). Log field IDs / "
        "lengths / types / counts, never the value or transcript text -- and "
        "never print() raw args/values to stdout:\n  "
        + "\n  ".join(f"{rel}:{ln}: {txt}" for ln, txt in offenders)
    )


def test_guard_catches_known_leaks():
    """Meta-test: the scanner flags known-bad shapes (incl. the variants the
    first version missed) and passes safe metadata lines."""
    # Single-line and the variants fresh-eyes flagged (value=selected_value, message=text).
    assert _scan_leaks('_log.info("X", sample=sample_values)')
    assert _scan_leaks("self._log.info('X', text_preview=transcription.text[:50])")
    assert _scan_leaks("_log.warning('X', value=selected_value)")
    assert _scan_leaks("self._log.debug('TEXT_MESSAGE_QUEUED', message=text)")
    # Multi-line log call with the kwarg on its own line.
    assert _scan_leaks('_log.debug(\n    "checkbox_group_filled",\n    value=selected_value,\n)')
    # Safe metadata must NOT flag.
    assert not _scan_leaks('_log.info("X", field_id=fid, value_length=len(v), value_type=t)')
    assert not _scan_leaks("self._log.debug('X', message_length=len(text))")
    # A constant-string message is safe (can't carry runtime PII).
    assert not _scan_leaks('_log.error("X", message="Session closed and cleaned up")')
    # A value assignment OUTSIDE a log call must NOT flag.
    assert not _scan_leaks('value_str = str(value)\nmessage = f"...{value_str}"')


def test_guard_catches_print_leaks():
    """The print()-sink scanner flags raw-arg/value prints (bd oeq) but leaves
    safe-metadata prints and constant prints alone."""
    # The exact bd-oeq leak shape and close variants.
    assert _scan_print_leaks('print(f"Arguments: {arguments}")')
    assert _scan_print_leaks('print(f"value={value}")')
    assert _scan_print_leaks("print(f'transcript: {transcript[:50]}')")
    assert _scan_print_leaks('print(f"{field_values}")')
    # Safe: interpolating only metadata names must NOT flag.
    assert not _scan_print_leaks('print(f"Tool: {tool_name}")')
    assert not _scan_print_leaks('print(f"arg_count={arg_count}")')
    assert not _scan_print_leaks("print(f\"{'='*80}\")")
    # A word-boundaried near-miss name must NOT flag (field_values_count is meta).
    assert not _scan_print_leaks('print(f"{field_values_count}")')
    # A non-print line interpolating a value must NOT be caught here (that's the
    # _log scanner's job, or it's a legitimate assignment).
    assert not _scan_print_leaks('result = f"...{value}"')
