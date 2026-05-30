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

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Files that handle raw field values / user-speech transcripts and log heavily.
GUARDED_FILES = [
    "backend/routes/pdf_fill_routes.py",
    "backend/adapters/live_ai_gemini.py",
]

# Log-call kwargs / slices that would emit a VALUE or TEXT rather than metadata.
# Each pattern targets a leak that bd hjo removed. Length/type/count/id-only
# kwargs (value_length=, value_type=, has_value=, message_length=, *_count=,
# field_id=, sample_field_ids=) are explicitly NOT matched -- those are safe.
LEAK_PATTERNS = [
    re.compile(r"\bsample=sample_values\b"),          # field_id:value dict
    re.compile(r"\btext_preview\s*="),                # transcript/message slice
    re.compile(r"=\s*transcription\.text\b"),         # raw transcript text
    re.compile(r"\bmessage\s*=\s*[A-Za-z_]+\[:\d+\]"),  # message=text[:100]
    re.compile(r"\bvalue\s*=\s*value\b"),             # value=value
    re.compile(r"\bselected_value\s*=\s*selected_value\b"),
    re.compile(r"\bselected_values\s*=\s*value\b"),
    re.compile(r"\btarget_value\s*=\s*target_value\b"),
    re.compile(r"\boriginal_value\s*=\s*value\b"),
    re.compile(r"\bavailable_options\s*="),           # leaks the form's option set
]


def _log_call_lines(path: pathlib.Path):
    """Yield (lineno, text) for lines that are part of a `_log.*(` call.

    Crude but sufficient: a leak kwarg only matters inside a log call. We match
    any line containing a `_log.` invocation OR a continuation line of one (the
    repo's multi-line log calls indent kwargs under the opening `_log.(`).
    Scanning ALL lines for the leak patterns is also safe here because the
    patterns (e.g. `value=value`) don't occur in normal assignment style.
    """
    return list(enumerate(path.read_text(encoding="utf-8").splitlines(), 1))


@pytest.mark.parametrize("rel", GUARDED_FILES)
def test_no_value_or_transcript_in_logs(rel):
    path = REPO_ROOT / rel
    assert path.exists(), f"guarded file missing: {rel}"
    offenders = []
    for lineno, line in _log_call_lines(path):
        # Ignore comment-only lines (our redaction notes mention "value").
        code = line.split("#", 1)[0]
        for pat in LEAK_PATTERNS:
            if pat.search(code):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "PII/PHI logging leak re-introduced (bd hjo). Log field IDs / "
        "lengths / types / counts, never the value or transcript text:\n  "
        + "\n  ".join(offenders)
    )


def test_guard_patterns_would_catch_a_leak():
    """Meta-test: the patterns actually match a known-bad line (no silent no-op)."""
    bad = '_log.info("pdf_fill_sample_values", kit=k, sample=sample_values)'
    assert any(p.search(bad) for p in LEAK_PATTERNS)
    bad2 = "self._log.info('X', text_preview=transcription.text[:50])"
    assert any(p.search(bad2) for p in LEAK_PATTERNS)
    # A safe line must NOT match.
    safe = '_log.info("pdf_fill", field_id=fid, value_length=len(v), value_type=t)'
    assert not any(p.search(safe.split("#", 1)[0]) for p in LEAK_PATTERNS)
