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
# These get an EXPLICIT per-file parametrized test (clear per-file failure
# messages); the broader `test_no_pii_logging_anywhere_in_backend` sweep below
# then covers EVERY non-test backend file so a NEW logging site can't escape the
# guard just because nobody added it here (bd polyglot-pdf-uov.15).
GUARDED_FILES = [
    "backend/routes/pdf_fill_routes.py",
    "backend/adapters/live_ai_gemini.py",
    # on_tool_call receives Gemini's tool args, which include field VALUES; it
    # previously print()'d them whole (bd polyglot-pdf-oeq).
    "backend/services/callback_handler.py",
    # Added bd polyglot-pdf-uov.15 after the all-backend sweep caught live leaks
    # these files had been escaping (they were never in the hand-maintained list):
    #   request_coordinator.py logged spoken_name=spoken_name (user-speech label);
    #   form_filling_service.py logged message=message (rendered text w/ field hint);
    #   websocket_routes.py is the fill/voice control plane.
    "backend/services/request_coordinator.py",
    "backend/services/form_filling_service.py",
    "backend/routes/websocket_routes.py",
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
    # spoken_name is a user-speech-derived label (get_field_value); it is now
    # logged as spoken_name_length=len(...) and must never carry the raw value
    # again (bd polyglot-pdf-t1c). spoken_name_length matches the *_length
    # safe-RHS, so the redacted form passes while spoken_name=spoken_name fails.
    "spoken_name",
)
# `fields` is a SPECIAL case: logging the field IDs (dict KEYS) is always-safe
# per the PII policy, but the same kwarg carrying field .values() would be a
# leak. So `fields` is not in _SENSITIVE_KWARGS (which would flag the safe
# keys() form); instead it has its own pattern that flags ONLY a .values()/
# values-bearing RHS (bd polyglot-pdf-t1c).
# Matched against the ACCUMULATED text of a single _log.* call (comments already
# stripped, lines joined with spaces), so a `fields=` / `.values(` split across
# source lines is still caught. The negated class excludes `,` and `)` so it
# stops at the kwarg boundary, but NOT `\n` (the buffer has none) -- the join is
# what lets it span lines.
_FIELDS_VALUES_LEAK = re.compile(r"\bfields\s*=\s*[^,)#]*\.values\s*\(")
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
    call_buf = ""       # accumulated in-call text for the current _log.* call
    call_start_line = 0  # where the current call opened (for fields-leak reporting)
    for lineno, raw in enumerate(text.splitlines(), 1):
        code = raw.split("#", 1)[0]
        if depth == 0:
            m = _LOG_CALL_START.search(code)
            if not m:
                continue
            depth = 1  # entered a log call on this line
            code_after = code[m.end():]
            call_buf = ""
            call_start_line = lineno
        else:
            code_after = code
        # Scan the in-call portion for sensitive kwargs that aren't safe metadata.
        for pat in LEAK_PATTERNS:
            for mm in pat.finditer(code_after):
                if _is_leak(mm):
                    offenders.append((lineno, raw.strip()))
                    break
        # Accumulate the call text so a `fields=` / `.values(` split across lines
        # is still caught (the single-line check would miss it).
        call_buf += " " + code_after
        # Update paren depth; when it returns to 0 the call has closed.
        depth += code_after.count("(") - code_after.count(")")
        if depth <= 0:
            # `fields=...values()` is a leak even though `fields` is otherwise
            # safe (it carries field IDs/keys); flag only the values-bearing form,
            # checked against the whole (possibly multi-line) call.
            if _FIELDS_VALUES_LEAK.search(call_buf):
                offenders.append((call_start_line, text.splitlines()[call_start_line - 1].strip()))
            depth = 0
            call_buf = ""
    return offenders


# Sensitive identifiers that must never be interpolated into a positional sink
# like print(). `_log.*(...)` kwargs are covered by _scan_leaks above; this is
# the OTHER class of leak (bd polyglot-pdf-oeq): `print(f"Arguments: {arguments}")`
# dumps the whole tool-call args, and `print(f"Response: {resp.response}")` dumps a
# tool response (get_field_value / get_form_status can carry field VALUES) -- both
# to stdout -> Cloud Run logs. We flag a sensitive base name interpolated into an
# f-string, INCLUDING when it is the base of an attribute/index/call access
# (`resp.response`, `args["k"]`, `x.value`). Safe-metadata names (tool_name,
# *_id, *_count, ...) are not in the list, so `{tool_name}`/`{arg_count}` are fine.
# This list is the print-sink counterpart of _SENSITIVE_KWARGS; keep them roughly
# aligned, and add the response/payload-style names a print is more apt to dump.
_SENSITIVE_IDENTS = (
    "arguments", "args", "value", "values", "selected_value", "selected_values",
    "target_value", "original_value", "message", "text", "text_preview",
    "transcript", "sample", "available_options", "system_instruction",
    "field_values", "current_values", "payload", "response", "resp", "state",
)
# A `{...}` interpolation whose expression references a sensitive base name --
# either bare (`{value}`) or as the base of `.attr` / `[idx]` / `(...)`
# (`{resp.response}`, `{args['k']}`). The base name is bounded by `{` or non-word
# on the left and by a non-word char (`.`/`[`/`(`/`}`/space) on the right, so
# `field_values_count` (a metadata name) does NOT match.
_FSTRING_SENSITIVE = re.compile(
    r"\{[^{}]*?(?<![\w.])(?:" + "|".join(re.escape(i) for i in _SENSITIVE_IDENTS) + r")\b[^{}]*\}"
)
_PRINT_CALL = re.compile(r"(?:^|[^\w.])print\s*\(")


def _scan_print_leaks(text: str):
    """Return [(lineno, line)] for print() calls interpolating a sensitive var.

    Depth-tracks MULTI-LINE print() calls (like _scan_leaks does for _log.*), so a
    `print(\\n    f"{arguments}")` split across lines is still caught. Flags a print
    whose f-string interpolates a sensitive base name (bare or `.attr`/`[idx]`).
    Comments are stripped first so a redaction note can't false-positive; a
    safe-metadata interpolation (`{tool_name}`, `{arg_count}`) does not match.
    """
    offenders = []
    depth = 0           # open-paren depth of the current print() call, 0 = not in one
    start_lineno = 0    # line where the current print() opened
    start_raw = ""
    flagged = False     # whether a sensitive interpolation was seen in this call
    for lineno, raw in enumerate(text.splitlines(), 1):
        code = raw.split("#", 1)[0]
        if depth == 0:
            m = _PRINT_CALL.search(code)
            if not m:
                continue
            depth = 1
            start_lineno, start_raw, flagged = lineno, raw, False
            code_after = code[m.end():]
        else:
            code_after = code
        if _FSTRING_SENSITIVE.search(code_after):
            flagged = True
        depth += code_after.count("(") - code_after.count(")")
        if depth <= 0:  # the print() call closed
            if flagged:
                offenders.append((start_lineno, start_raw.strip()))
            depth = 0
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


# Directories/name-prefixes under backend/ that are NOT production logging sites:
# tests assert on PII deliberately, and one-off probe/dev scripts are never on the
# Cloud Run request path (they run locally, by hand). Everything else in backend/
# CAN reach production stdout -> Cloud Logging, so it must be guarded.
_SWEEP_SKIP_DIR_PARTS = ("tests", "scripts", "__pycache__")
_SWEEP_SKIP_NAME_PREFIXES = ("test_", "probe_")


def _all_backend_source_files() -> list[pathlib.Path]:
    """Every production backend .py file (excludes tests, probes, dev scripts).

    This is the completeness backstop: the hand-maintained GUARDED_FILES list
    inevitably lags new files, and an unguarded new file is exactly how a leak
    ships silently. Sweeping ALL of backend/ means a new logging site is covered
    the moment it lands, with no list edit (bd polyglot-pdf-uov.15)."""
    out = []
    backend = REPO_ROOT / "backend"
    for p in sorted(backend.rglob("*.py")):
        rel_parts = p.relative_to(REPO_ROOT).parts
        if any(part in _SWEEP_SKIP_DIR_PARTS for part in rel_parts):
            continue
        if any(p.name.startswith(pre) for pre in _SWEEP_SKIP_NAME_PREFIXES):
            continue
        out.append(p)
    return out


def test_no_pii_logging_anywhere_in_backend():
    """Completeness sweep: NO production backend file may log a value/transcript.

    Unlike the per-file GUARDED_FILES test, this scans every non-test backend
    source file, so a leak in a file nobody thought to guard still fails the
    suite. GUARDED_FILES remains for targeted, well-labelled regression coverage;
    this is the net under it (bd polyglot-pdf-uov.15)."""
    files = _all_backend_source_files()
    # Guard the guard: refuse to pass on a partial/empty sweep. The backend has
    # ~40 production modules today; a floor of 20 catches a broken glob that found
    # nothing OR a path bug that silently halved the set (a "found >5, looks fine"
    # partial sweep would otherwise pass while skipping most files -- fresh-eyes
    # PR for this bead). The floor is deliberately well below the real count so
    # legitimate refactors don't trip it; it only fires on a gross under-count.
    assert len(files) >= 20, (
        f"backend source sweep found only {len(files)} files (expected ~40) -- the "
        f"path glob is probably wrong (REPO_ROOT={REPO_ROOT}); refusing to pass on "
        f"a partial sweep."
    )

    all_offenders: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        offenders = _scan_leaks(text) + _scan_print_leaks(text)
        rel = path.relative_to(REPO_ROOT).as_posix()
        all_offenders.extend(f"{rel}:{ln}: {txt}" for ln, txt in offenders)

    assert not all_offenders, (
        "PII/PHI logging leak in a backend file (bd polyglot-pdf-uov.15 sweep). "
        "Log field IDs / lengths / types / counts, never the value or transcript "
        "text, and never print() raw args/values to stdout:\n  "
        + "\n  ".join(all_offenders)
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
    # spoken_name: the raw value is a leak; the redacted length form is safe (bd t1c).
    assert _scan_leaks('_log.info("X", spoken_name=spoken_name, found=f)')
    assert not _scan_leaks('_log.info("X", spoken_name_length=len(spoken_name), found=f)')
    # fields: keys() (field IDs) are safe; values() is a leak (bd t1c).
    assert not _scan_leaks('_log.warning("X", fields=list(updates.keys()), n=c)')
    assert _scan_leaks('_log.warning("X", fields=list(updates.values()), n=c)')
    # fields=...values() SPLIT across lines is still caught (multi-line call).
    assert _scan_leaks('_log.warning(\n    "X",\n    fields=list(\n        updates.values()\n    ),\n)')
    # The safe multi-line keys() form must still NOT flag.
    assert not _scan_leaks('_log.warning(\n    "X",\n    fields=list(\n        updates.keys()\n    ),\n)')


def test_guard_catches_print_leaks():
    """The print()-sink scanner flags raw-arg/value prints (bd oeq) but leaves
    safe-metadata prints and constant prints alone."""
    # The exact bd-oeq leak shape and close variants.
    assert _scan_print_leaks('print(f"Arguments: {arguments}")')
    assert _scan_print_leaks('print(f"value={value}")')
    assert _scan_print_leaks("print(f'transcript: {transcript[:50]}')")
    assert _scan_print_leaks('print(f"{field_values}")')
    # ATTRIBUTE/INDEX access on a sensitive base must flag (the live_ai_gemini.py
    # `print(f"Response: {resp.response}")` leak Copilot found on PR #48).
    assert _scan_print_leaks('print(f"Response: {resp.response}")')
    assert _scan_print_leaks('print(f"{args[\'field_id\']}")')
    assert _scan_print_leaks('print(f"{value.upper()}")')
    # MULTI-LINE print() call with the sensitive interpolation on a later line.
    assert _scan_print_leaks('print(\n    f"Response: {resp.response}"\n)')
    # Safe: interpolating only metadata names must NOT flag.
    assert not _scan_print_leaks('print(f"Tool: {tool_name}")')
    assert not _scan_print_leaks('print(f"arg_count={arg_count}")')
    assert not _scan_print_leaks("print(f\"{'='*80}\")")
    assert not _scan_print_leaks('print(f"chars={response_chars}, ~{estimated_tokens} tokens")')
    # A word-boundaried near-miss name must NOT flag (field_values_count is meta;
    # response_chars/response_str share the `response` prefix but are metadata).
    assert not _scan_print_leaks('print(f"{field_values_count}")')
    assert not _scan_print_leaks('print(f"{response_chars}")')
    # `pprint(...)` must not be mistaken for `print(...)` (word-boundary on print).
    assert not _scan_print_leaks('pprint(f"{summary}")')
    # A non-print line interpolating a value must NOT be caught here (that's the
    # _log scanner's job, or it's a legitimate assignment).
    assert not _scan_print_leaks('result = f"...{value}"')
