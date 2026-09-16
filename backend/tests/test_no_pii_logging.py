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
import ast
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
    # The text-model adapter (validator, secretary, translation calls): its
    # prompts and completions ARE field values (bd polyglot-pdf-wfgjz).
    # secretary_context.py builds the prompt and has no log call at all; the
    # deny-by-default sweep below covers it the day one appears.
    "backend/adapters/text_ai_gemini.py",
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
    # spoken_name is a user-speech-derived label (formerly get_field_value,
    # retired bd polyglot-pdf-p5h2; the pattern is a standing guard against
    # any future spoken-name logging site); it is now logged as
    # spoken_name_length=len(...) and must never carry the raw value again
    # (bd polyglot-pdf-t1c). spoken_name_length matches the *_length safe-RHS,
    # so the redacted form passes while spoken_name=spoken_name fails.
    "spoken_name",
    # The exception-MESSAGE class (bd polyglot-pdf-2kbo0, sprint 23 B1b):
    # `error=str(exc)` carries whatever the exception rendered, and a
    # ValueError from a field validator renders the field VALUE. The
    # sanctioned shape is error_type=type(exc).__name__ (a different kwarg
    # name, so it does not match here) -- e4dt8's processor supplies type +
    # frames for _log.exception(); a plain _log.warning has only this guard.
    # `detail` is the same class (HTTP detail strings echo the request).
    "error", "err", "exc", "detail",
    # A hand-formatted traceback string (traceback.format_exc()) ends with the
    # exception MESSAGE line, so it is the same class; exc_info=True is the
    # sanctioned shape (e4dt8's processor renders frames + type, no message).
    "traceback", "tb", "stack", "stacktrace",
)

# Per-site allowlist for the error-class kwargs: EXACT (file, kwarg text)
# pairs that carry a non-literal that is known not to be client data, each
# with its reason. test_allowlisted_error_sites_still_exist pins the list
# against the tree so a removed site leaves no dead entry (scar #8).
_ERROR_KWARG_ALLOWLIST = {
    # The extractor subprocess's last stderr line: it runs on a BLANK form
    # PDF (kit authoring), never on client data, and the tail is capped.
    ("backend/routes/editor_kit_routes.py", "detail=last_line[:400]"):
        "extractor stderr tail; blank-form PDF, no client data",
}
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
# The error class is matched with ANY prefix (final_error=, last_exc=, ...):
# `\b` never fires after an underscore, so a plain `\berror=` let
# final_error=str(e) through (bd 2kbo0 fresh-eyes). The name-suffix forms
# error_type= / error_count= still do not match: `=` must follow the word.
_PREFIXED_KWARGS = ("error", "err", "exc", "traceback", "detail", "tb", "stack", "stacktrace")
LEAK_PATTERNS = [
    re.compile(
        (r"\b[A-Za-z0-9_]*" if k in _PREFIXED_KWARGS else r"\b")
        + re.escape(k) + r"\s*=\s*(?P<rhs>[^,)\n#]+)"
    )
    for k in _SENSITIVE_KWARGS
]


def _is_leak(match) -> bool:
    """A sensitive kwarg is a leak unless its RHS is a safe metadata wrapper."""
    rhs = match.group("rhs")
    return not _SAFE_RHS.match(rhs)


# Every logger spelling the tree uses (_log / log / logger, bare or on self,
# and the inline structlog.get_logger() form)
# and every level INCLUDING .exception( -- the first version matched only
# `_log.` and five levels, so a `_log.exception(..., error=str(exc))` and
# every `log.`/`logger.` file escaped the sweep (bd 2kbo0 mutation catch).
_LOG_CALL_START = re.compile(
    r"(?:self\.)?(?:_log|log|logger|structlog\.get_logger\(\))\.(?:info|warn|warning|error|debug|critical|exception)\s*\("
    r"|get_structured_logger\(\)\.(?:log_text_ai_usage|log_tts_usage|"
    r"log_gemini_api_response)\s*\("
)


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
# tool response (ask_secretary / get_form_status can carry field VALUES) -- both
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
    # The exception-message class (sprint 23 B1b): `{e}` / `{str(exc)}` in a
    # print renders the message, and stdout IS Cloud Logging on Cloud Run.
    # `{type(e).__name__}` is the sanctioned shape -- and it matches here
    # too, so the scanner exempts a `type(<ident>).__name__` interpolation.
    "e", "exc", "err", "error", "last_exc", "tb", "traceback",
)
_EXC_CLASS_ONLY = re.compile(r"\{type\([A-Za-z_][A-Za-z0-9_]*\)\.__name__[^{}]*\}")
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
        if _FSTRING_SENSITIVE.search(_EXC_CLASS_ONLY.sub("{}", code_after)):
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
# Cloud Run request path (they run locally, by hand). The virtualenv
# (backend/.venv, holding third-party site-packages) is vendored dependency code,
# not this project's source -- its print()s are not our logging sites and must not
# be swept. Everything else in backend/ CAN reach production stdout -> Cloud
# Logging, so it must be guarded.
_SWEEP_SKIP_DIR_PARTS = (
    "tests", "scripts", "__pycache__", ".venv", "venv", "site-packages",
)
_SWEEP_SKIP_NAME_PREFIXES = ("test_", "probe_")


def _all_backend_source_files() -> list[pathlib.Path]:
    """Every production .py file of BOTH services (backend/ and admin_backend/;
    excludes tests, probes, dev scripts).

    This is the completeness backstop: the hand-maintained GUARDED_FILES list
    inevitably lags new files, and an unguarded new file is exactly how a leak
    ships silently. Sweeping ALL of backend/ means a new logging site is covered
    the moment it lands, with no list edit (bd polyglot-pdf-uov.15)."""
    out = []
    for root in ("backend", "admin_backend"):
      for p in sorted((REPO_ROOT / root).rglob("*.py")):
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
        all_offenders.extend(
            f"{rel}:{ln}: {txt}" for ln, txt in offenders
            if not _is_allowlisted(rel, txt)
        )

    assert not all_offenders, (
        "PII/PHI logging leak in a backend file (bd polyglot-pdf-uov.15 sweep). "
        "Log field IDs / lengths / types / counts, never the value or transcript "
        "text, and never print() raw args/values to stdout:\n  "
        + "\n  ".join(all_offenders)
    )


def _is_allowlisted(rel: str, line_text: str) -> bool:
    """True when the offending line carries EXACTLY an allowlisted kwarg text
    at an allowlisted file -- exact text, so a widened RHS is not covered."""
    return any(f == rel and kwarg_text in line_text.replace(" ", "")
               for (f, kwarg_text) in _ERROR_KWARG_ALLOWLIST)


def test_allowlisted_error_sites_still_exist():
    """Every allowlist entry must still match a line in its file, so a
    site that moves or disappears takes its exemption with it."""
    for (rel, kwarg_text) in _ERROR_KWARG_ALLOWLIST:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8").replace(" ", "")
        assert kwarg_text in text, f"stale allowlist entry: {rel} {kwarg_text}"


def test_the_sweep_covers_the_admin_service():
    """The admin service logs too (bd 2kbo0 found 40 error=str(exc) sites
    there); the sweep must include it, not just backend/."""
    rels = {p.relative_to(REPO_ROOT).parts[0] for p in _all_backend_source_files()}
    assert rels == {"backend", "admin_backend"}, rels


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
    # The exception-message class (bd 2kbo0): error=str(exc) is a leak on any
    # level; the sanctioned error_type=type(exc).__name__ is not, nor is
    # exc_info=True (a different kwarg; e4dt8's processor redacts it).
    assert _scan_leaks('_log.warning("X", error=str(exc))')
    assert _scan_leaks('_log.exception("X", error=str(exc))')
    assert _scan_leaks('_log.error("X", traceback=traceback.format_exc())')
    assert _scan_leaks('self._log.warn("X", error=str(e))')
    assert _scan_leaks('structlog.get_logger().warning("X", detail=body)')
    assert not _scan_leaks('structlog.get_logger().warning("X", detail="fixed text")')
    assert _scan_leaks('self._log.error("X", attempts=n, final_error=str(e))')
    assert _scan_leaks('_log.error("X", last_exc=exc)')
    assert _scan_leaks('_log.error("X", last_detail=body, final_tb=tb)')
    assert not _scan_leaks('_log.error("X", is_name_error=bool(is_name_err), returning_error=True)')
    assert not _scan_leaks('_log.error("X", final_error_type=type(e).__name__, error_count=n)')
    assert _scan_leaks('self._log.error("X", error_type=type(e).__name__, traceback=tb)')
    assert not _scan_leaks('_log.error("X", error_type=type(e).__name__, exc_info=True)')
    assert _scan_leaks('log.exception("X", error=str(exc))')
    assert _scan_leaks('logger.warning("X", value=value)')
    assert _scan_leaks('self._log.exception("X", detail=body)')
    assert _scan_leaks('_log.error(\n    "X",\n    error=str(e),\n)')
    assert _scan_leaks('_log.info("X", detail=resp.text[:200])')
    assert not _scan_leaks('_log.error("X", error_type=type(exc).__name__)')
    assert not _scan_leaks('_log.error("X", exc_info=True)')
    assert not _scan_leaks('_log.warning("X", error_count=len(errs), err_id=eid)')
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
    # The exception-message class in a print (sprint 23 B1b); the class-only
    # shape is exempt.
    assert _scan_print_leaks('print(f"Error: {str(e)}")')
    assert _scan_print_leaks('print(f"Failed to build {field_id}: {e}")')
    assert _scan_print_leaks('print(f"Previous: {str(last_exc) if last_exc else 1}")')
    assert not _scan_print_leaks('print(f"Error: {type(e).__name__}")')
    assert not _scan_print_leaks('print(f"Previous: {type(last_exc).__name__ if last_exc else 1}")')
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

# ===========================================================================
# The EXCEPTION-MESSAGE leak (bd polyglot-pdf-p84m P0 / polyglot-pdf-e4dt8)
# ===========================================================================
#
# Everything above this line is a SOURCE-LEVEL grep guard: it reads the repo's
# text and flags a log call that names a sensitive kwarg. That shape of guard
# is structurally blind to this leak, because the leaking call looks perfectly
# clean in source:
#
#     self._log.exception("tool_callback_error", tool=tool_name)
#
# No value kwarg, no transcript, nothing to grep for. The PII arrives at
# RENDER time, from structlog's processor chain, which used to run
# format_exc_info -- and that processor writes the exception MESSAGE into the
# JSON output. In a form-filling app that message routinely embeds a field
# value: a parse error over an A-number, a validation error naming a date of
# birth.
#
# So this case is a RUNTIME test in a file of static ones, deliberately. It
# drives a real exception through the real production chain and asserts the
# sentinel never appears. The deeper shape assertions (frames present, type
# present, chained causes, exc_info=True, source text, locals) live in
# backend/tests/unit/test_error_shape.py; what belongs HERE is the one
# question this file is the home for: did user data reach the log?


def test_an_exception_message_never_reaches_the_log():
    """RED before bd polyglot-pdf-e4dt8, green after.

    Mutation-verified by restoring structlog.processors.format_exc_info in
    backend/utils/logging.py's chain -- the sentinel reappears and this goes
    red.
    """
    import io as _io
    import logging as _logging

    import structlog

    from backend.utils.logging import configure_logging

    sentinel = "A-098-765-432-PII-SENTINEL"

    stream = _io.StringIO()
    root = _logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    handler = _logging.StreamHandler(stream)
    handler.setFormatter(_logging.Formatter("%(message)s"))
    root.handlers = [handler]
    root.setLevel(_logging.DEBUG)

    try:
        configure_logging()
        log = structlog.get_logger("test_no_pii_logging")
        try:
            # The shape that actually occurs: a field value interpolated
            # into the message of an exception raised while handling it.
            raise ValueError("could not parse alien number " + sentinel)
        except ValueError:
            log.exception("tool_callback_error", tool="update_form_fields")
        rendered = stream.getvalue()
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        structlog.reset_defaults()

    assert rendered.strip(), (
        "nothing was logged -- the assertion below would pass vacuously")
    assert sentinel not in rendered, (
        "the exception MESSAGE reached the rendered log line, carrying what "
        "stands in for a field value straight to Cloud Logging "
        "(bd polyglot-pdf-p84m, a P0). Rendered: " + rendered)
    # And the log is still USEFUL -- a guard that passed by emitting nothing
    # would trade a PII leak for a debugging blackout.
    assert "ValueError" in rendered, (
        "the exception TYPE was dropped along with the message; the error is "
        "now undebuggable and invisible to Cloud Error Reporting")



# ---------------------------------------------------------------------------
# Sprint 23 B1a (bd polyglot-pdf-wfgjz): two more sinks a field value could
# take out of the process -- the 422 response body, and the WebSocket close
# reason on the wire.
# ---------------------------------------------------------------------------

_B1A_SENTINEL = "A-098-765-432-PII-SENTINEL"


def test_a_422_never_echoes_the_request_body():
    """RED before backend/utils/validation_errors.py was installed on the
    app (FastAPI's default 422 carries each error's `input`), green after.
    Mutation-verified by removing install_validation_error_handler(app)
    from backend/main.py."""
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    # /api/disclaimer-acceptance is unauthenticated and takes a pydantic
    # body; a string where an int is expected is the malformed shape.
    resp = client.post("/api/disclaimer-acceptance", json={
        "form_session_id": "fs-sentinel-test",
        "language": "en",
        "timestamp": _B1A_SENTINEL,
    })
    assert resp.status_code == 422, resp.text
    assert _B1A_SENTINEL not in resp.text, (
        "the 422 body echoed the request value back: " + resp.text)
    detail = resp.json()["detail"]
    assert detail and all(set(e) <= {"loc", "type", "msg"} for e in detail), detail
    assert any("timestamp" in e["loc"] for e in detail), detail


def test_a_422_never_echoes_a_value_through_a_custom_validator_message():
    """The second echo channel: a route validator's `raise ValueError(f"...{v}...")`
    is rendered by pydantic into `msg` verbatim. disclaimer_routes bounds the
    timestamp that way, so an in-type but out-of-range value is the sentinel
    here (a type mismatch never reaches the custom validator). RED with `msg`
    passed through for value_error; mutation-verified by removing the
    _CUSTOM_MESSAGE_TYPES replacement."""
    from fastapi.testclient import TestClient

    from backend.main import app

    sentinel_ts = 100000001  # ms; far below the route's minimum, in type
    resp = TestClient(app).post("/api/disclaimer-acceptance", json={
        "form_session_id": "fs-sentinel-test", "language": "en", "timestamp": sentinel_ts})
    assert resp.status_code == 422, resp.text
    assert str(sentinel_ts) not in resp.text, (
        "the custom validator message carried the submitted value into the 422: " + resp.text)
    assert any(e["type"] == "value_error" for e in resp.json()["detail"]), resp.text


def test_the_backend_app_is_not_in_debug_mode():
    """A debug app renders tracebacks, locals included, into 500 bodies."""
    from backend.main import app

    assert app.debug is False


# --- the close reason on the wire is always a static literal --------------

# Independent statement of the wire reasons /ws/fill may send. Written out
# here, not derived from the route, so a new site that sends anything else
# (an f-string, str(exc), a client-supplied token) fails below. The
# reason_token (telemetry only) is e4dt8's set; this is the ON-THE-WIRE text.
WS_WIRE_CLOSE_REASONS = frozenset({
    "",  # the default: most closes send no reason
    "Idle timeout",
    "Authentication failed",
    "This account is not enrolled for the voice application",
    "budget_exhausted",
    "budget_unavailable",
    # Sprint 23 C2: the Origin allowlist, the frame cap and the staff
    # kit-scope refusal, each a fixed phrase.
    "Origin not allowed",
    "Frame too large",
    "Kit not available",
    "kit_unavailable",
})

_WS_ROUTES = REPO_ROOT / "backend" / "routes" / "websocket_routes.py"


def _literal_strings(node: ast.AST) -> set:
    """Every string a reason expression can evaluate to, or raise if any
    branch is not a literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _literal_strings(node.body) | _literal_strings(node.orelse)
    if isinstance(node, ast.BoolOp):
        out = set()
        for v in node.values:
            out |= _literal_strings(v)
        return out
    raise AssertionError("non-literal close reason expression at line %d: %s"
                         % (node.lineno, ast.dump(node)[:120]))


def _reason_expression(call: ast.Call, enclosing: ast.AST) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg != "reason":
            continue
        if isinstance(kw.value, ast.Name):
            # Resolve the last assignment to that name before the call, inside
            # the enclosing function.
            assigned = None
            # Same function only: a nested def/lambda is its own scope.
            nodes = [n for n in ast.walk(enclosing)
                     if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
                     or n is enclosing]
            for n in nodes:
                if (isinstance(n, ast.Assign) and n.lineno < call.lineno
                        and any(isinstance(t, ast.Name) and t.id == kw.value.id for t in n.targets)):
                    if assigned is None or n.lineno > assigned.lineno:
                        assigned = n
            assert assigned is not None, (
                "reason=%s at line %d is never assigned a literal" % (kw.value.id, call.lineno))
            return assigned.value
        return kw.value
    return None


def _is_close_call(call: ast.Call) -> bool:
    f = call.func
    return ((isinstance(f, ast.Name) and f.id == "_close_ws")
            or (isinstance(f, ast.Attribute) and f.attr == "close"))


def test_every_ws_close_reason_is_a_static_literal_from_the_pinned_set():
    """A close reason built from a client string or an exception message
    would put that text on the wire (and into Cloud Run's WebSocket log).
    Every close site on the route must send a literal from
    WS_WIRE_CLOSE_REASONS. Mutation-verified by changing one site's literal
    to an f-string carrying the exception."""
    tree = ast.parse(_WS_ROUTES.read_text(encoding="utf-8"))
    seen: set = set()
    sites = 0
    for func in [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name != "_close_ws"]:  # the wrapper forwards its parameter
        for call in [n for n in ast.walk(func) if isinstance(n, ast.Call) and _is_close_call(n)]:
            sites += 1
            expr = _reason_expression(call, func)
            if expr is None:
                seen.add("")
                continue
            seen |= _literal_strings(expr)
    assert sites >= 8, "the close-site scan is vacuous: %d sites" % sites
    unexpected = seen - WS_WIRE_CLOSE_REASONS
    assert not unexpected, "unpinned wire close reasons: " + repr(sorted(unexpected))
    missing = WS_WIRE_CLOSE_REASONS - seen
    assert not missing, "pinned reasons no site sends any more: " + repr(sorted(missing))


@pytest.mark.asyncio
async def test_close_ws_puts_only_the_stated_reason_on_the_wire(capsys):
    """The wrapper's telemetry metadata (which may name an exception type or
    a mismatched id) must never leak into the wire reason: the peer receives
    exactly the literal the site stated. Mutation-verified by appending the
    reason_token to the wire reason inside _close_ws."""
    from unittest.mock import AsyncMock

    from backend.routes.websocket_routes import _close_ws

    ws = AsyncMock()
    await _close_ws(ws, 1008, "auth_failed", reason="Authentication failed",
                    metadata={"detail": _B1A_SENTINEL})
    ws.close.assert_awaited_once()
    kwargs = ws.close.await_args.kwargs
    assert kwargs["reason"] == "Authentication failed"
    assert _B1A_SENTINEL not in kwargs["reason"]
    capsys.readouterr()  # the counted close event (metadata is telemetry, not the wire)
