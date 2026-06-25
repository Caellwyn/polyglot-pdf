"""G1b scoring helpers -- STDLIB ONLY (no google.genai / no API SDK).

bd polyglot-pdf-0zp3. Extracted from the probe so the OFFLINE tools (g1b_merge.py
re-score, g1b_analyze.py) can import the scorer WITHOUT pulling in the probe's
google.genai import (Codex review: the offline merge must run with no API SDK
installed). The probe imports these too, so there is exactly one scorer.

Detection model: a labeled case carries one or more EXPECTED conflict GROUPS (each
a set of field ids that together constitute one contradiction). The model returns
FLAGGED groups (each a set of field ids it flagged together). A case is DETECTED
only if, for EVERY expected group, some flagged group COVERS it -- i.e. every
field in the expected group is matched (prefix-tolerant) by some field in that one
flagged group. This is full-group matching, NOT "any expected field appears in any
flag" (Codex review: any-overlap inflated far-distance recall, since a model that
flagged only the nearby half of a cross-section pair was wrongly counted as a
catch).
"""
from __future__ import annotations

# Field-id stem length below which a prefix match is too loose to trust. The voice
# model truncates ids to the line stem ('p1_line6e' for 'p1_line6e_state'); a bare
# 'p1' or 'p1_line6' must NOT match every p1_line6* field.
_MIN_PREFIX = len("p1_line6e")  # 9 chars -- the line+letter stem


def ids_match(a: str, b: str) -> bool:
    """True if two field ids refer to the same field: equal, OR one is a prefix of
    the other AND the shorter id reaches at least the line+letter stem. The
    native-audio (voice) model truncates ids in its tool call, so exact matching
    wrongly scored those as misses; for full-length text-model ids this reduces to
    equality."""
    if a == b:
        return True
    short, lng = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= _MIN_PREFIX and lng.startswith(short)


def _group_covered(expected_group: set, flagged_group: set) -> bool:
    """Every field in expected_group is matched (prefix-tolerant) by some field in
    flagged_group."""
    return all(any(ids_match(ef, ff) for ff in flagged_group) for ef in expected_group)


def detected(expected: list, flagged: list) -> bool:
    """Full-group detection. `expected` and `flagged` are lists of field-id SETS.
    A case is detected iff EVERY expected group is covered by SOME flagged group.
    Empty `expected` (a clean case) is never 'detected'."""
    if not expected:
        return False
    for exp in expected:
        if not any(_group_covered(exp, fl) for fl in flagged):
            return False
    return True
