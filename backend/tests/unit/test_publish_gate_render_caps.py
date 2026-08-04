"""The publish gate's finding-render caps are load-bearing (bd xfdb).

The 409 detail is the one surface where a reviewer is actively blocked
from marking a kit complete, and the bd-xfdb copy pass moved every
message's remedy clause to the END -- so the per-segment cap must be
large enough to keep the remedy, and the outer cap must never be the
binding constraint (8 x 400 + 7 x len("; ") = 3214 exactly; a smaller
outer cap re-cuts the 8th finding's remedy). These properties were both
violated once and fixed under review (Opus outer rounds); this pins them
the same way test_lint_rule_parity pins the label maps: by reading the
route source, because the expression is inline in the handler.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_ROUTES = _REPO / "backend" / "routes" / "editor_kit_routes.py"

SEGMENT_CAP = 400
FINDINGS_SHOWN = 8
OUTER_CAP = FINDINGS_SHOWN * SEGMENT_CAP + (FINDINGS_SHOWN - 1) * len("; ")


def _gate_block() -> str:
    src = _ROUTES.read_text(encoding="utf-8")
    m = re.search(
        r"shown = \"; \"\.join\((.*?)\n\s*more = ", src, re.DOTALL)
    assert m, "the gate's shown-expression was not found (renamed?)"
    return m.group(0)


def test_the_per_segment_cap_keeps_the_remedy_clause():
    block = _gate_block()
    m = re.search(r"\[:(\d+)\] for f in lint_errors\[:(\d+)\]", block)
    assert m, "per-segment cap / findings count not found in the expression"
    assert int(m.group(1)) == SEGMENT_CAP, (
        f"per-segment cap changed from {SEGMENT_CAP} to {m.group(1)} -- the "
        "bd-xfdb messages end with their remedy clause and were measured "
        "against 400; shrinking it re-cuts the instruction at the one gate "
        "where the reviewer is blocked."
    )
    assert int(m.group(2)) == FINDINGS_SHOWN


def test_the_outer_cap_is_never_the_binding_constraint():
    block = _gate_block()
    m = re.search(r"\)\[:(\d+)\]", block)
    assert m, "outer cap not found in the expression"
    assert int(m.group(1)) >= OUTER_CAP, (
        f"outer cap {m.group(1)} < {OUTER_CAP} (= {FINDINGS_SHOWN} x "
        f"{SEGMENT_CAP} + separators): the 8th finding's trailing remedy "
        "clause gets re-cut, the exact regression this cap was raised to "
        "fix (Opus outer review, measured)."
    )


def test_the_joined_worst_case_fits_the_outer_cap():
    # Pure arithmetic pin, independent of the source parse: eight maximal
    # segments joined must fit, so the per-segment cap is what binds.
    segments = ["x" * SEGMENT_CAP] * FINDINGS_SHOWN
    assert len("; ".join(segments)) == OUTER_CAP
