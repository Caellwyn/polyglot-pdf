"""Slice-anchoring guard for the voice-harness W-7 --trim artifact (bd
polyglot-pdf-r0za).

tests/e2e/voice-harness/apply_details_w7.py builds a trimmed variant of the
booklet's "Reason You're Submitting Form W-7" section as four verbatim slices:
section intro + category a, box h, Exception 1, Exception 2.

The booklet refers FORWARD to its own exceptions inside category f's prose
("attach the documents required under Exception 2."), so a naive
full.find("Exception 2.") lands ~2.9k chars before the real heading. That made
the Exception-2 slice start mid-category-f and re-include box h and all of
Exception 1 -- the slices overlapped and the artifact was 42% larger than its
docstring described. These tests pin the corrected anchoring.

No LLM, no network: reads the committed booklet PDF via PyMuPDF.
ASCII only (cp1252 safe).
"""

import importlib.util
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "tests" / "e2e" / "voice-harness" / "apply_details_w7.py"
_BOOKLET = _REPO / "form-kits" / "w7" / "w7-instructions.pdf"

pytestmark = pytest.mark.skipif(
    not _BOOKLET.exists() or not _SCRIPT.exists(),
    reason="w7 booklet PDF / harness script unavailable",
)


@pytest.fixture(scope="module")
def adw7():
    sys.path.insert(0, str(_SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("apply_details_w7", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_trimmed_slices_are_non_overlapping_and_ordered(adw7):
    """Exit criterion: the four slices must not overlap. Before the fix the
    Exception-2 slice started ~2.9k chars early and swallowed the two above it."""
    full = adw7.extract_reason_section()
    parts = adw7.extract_trimmed_section().split("\n\n")
    assert len(parts) == 4, [p[:40] for p in parts]

    spans = []
    for part in parts:
        start = full.find(part[:60])
        assert start >= 0, f"slice not found verbatim in the section: {part[:60]!r}"
        spans.append((start, start + len(part)))

    # Ascending and disjoint, in the order the function emits them.
    assert spans == sorted(spans), spans
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        assert prev_end <= next_start, spans


def test_exception_two_slice_starts_at_the_real_heading(adw7):
    """The Exception-2 slice must begin at the body heading, not at the
    category-f cross-reference that mentions Exception 2 in passing."""
    parts = adw7.extract_trimmed_section().split("\n\n")
    exc2 = parts[3]
    assert exc2.startswith("Exception 2. Other income."), exc2[:80]
    # The bug's signature: box-h and Exception-1 text duplicated into this slice.
    assert "h. Other." not in exc2
    assert "Exception 1." not in exc2


def test_trimmed_variant_is_smaller_than_the_full_section(adw7):
    """The whole point of --trim is fitting the ctu8-tuned compression window;
    the full section breached it (Vertex 1007). Guards against the trim silently
    regrowing toward the full section."""
    full = adw7.extract_reason_section()
    trimmed = adw7.extract_trimmed_section()
    assert len(trimmed) < len(full)
    # Comfortably under the ~3.4k-token full section that hard-failed.
    assert len(trimmed) < 5000, len(trimmed)


def test_no_heading_starts_two_different_slices(adw7):
    """No heading may OPEN more than one slice -- the overlap symptom.

    Deliberately not a whole-artifact substring count: the booklet legitimately
    refers back to "Exception 1." twice inside the Exception-1 body ("see
    Exceptions Tables ... on Exception 1", "aren't eligible for Exception 1"),
    and those are correct verbatim content. What must be unique is which slice a
    heading BEGINS.
    """
    parts = adw7.extract_trimmed_section().split("\n\n")
    for heading in ("h. Other.", "Exception 1.", "Exception 2. Other income."):
        starters = [p[:60] for p in parts if p.startswith(heading)]
        assert len(starters) == 1, (heading, starters)
