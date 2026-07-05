"""Deterministic pre-grouping CANDIDATES for the extractor prompt (bd h76m.12).

The W-7 failure that triggered the schema-v2 epic was a GROUPING failure: the
LLM had to consolidate 8 sibling checkboxes "by meaning" with no structural
help, and collapsed their identity instead. This module mines the acroform
dump for widget families that LOOK like one logical question and presents
them to the model as labeled CANDIDATES -- suggest, don't decide: the model
adopts a candidate as ONE field or splits it, based on the printed labels
only it can read.

Signals (all deterministic, no form-specific heuristics):
- same-leaf-multi-index: widgets sharing one leaf base with distinct [n]
  indexes (w9's c1_1[0..6]; w7's c1_11[0..3]) -- the strongest family signal,
  usually a radio-style exactly-one group.
- numbered-leaf-run: single-index widgets whose leaf bases differ only by a
  trailing number, in a consecutive run, sharing page + column + on-value
  (w7's c1_2..c1_9 reason boxes) -- the multi-checkbox family the W-7
  failure lost.
- shared-on-value / distinct-on-values: reported per candidate (distinct
  on-values on one shared name = true AcroForm radio kids -> v2
  pdf_on_value; shared "1" across distinct names = W-7-style checkboxes).
- column-aligned / row-aligned geometry: supporting evidence only.
- tooltip-prefix: when /TU tooltips exist and share a long common prefix.

Pure functions over the dump dict (acroform_dump.py's JSON shape); the
prompt block is rendered by render_candidates_block and injected by
arm_llm_native.build_prompt behind the group_candidates flag (default OFF;
extract_form --group-candidates turns it on; eval_extraction --extract
--group-candidates runs the ablation arm).

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from structural_enrich import decompose_name  # noqa: E402

# Column/row alignment tolerance (pt) and the max numeric gap inside a
# numbered run (c1_7 -> c1_8 on the W-7 sits ~24pt apart with instruction
# text between; the NUMBERS stay consecutive, which is the primary signal).
_ALIGN_TOL = 6.0
_MAX_NUM_GAP = 1  # run members must be numerically consecutive

_BUTTON_TYPES = {"checkbox", "radio"}


def _button_widgets(dump: dict) -> list[dict[str, Any]]:
    """Flatten button (checkbox/radio) widgets with their decomposed names."""
    out = []
    for f in dump.get("fields", []) or []:
        if f.get("logical_type") not in _BUTTON_TYPES:
            continue
        name = f.get("name") or ""
        dec = decompose_name(name)
        for w in f.get("widgets", []) or []:
            rect = w.get("rect") or {}
            out.append({
                "name": name,
                "leaf": dec["leaf"],          # leaf base, [n] stripped
                "index": dec["index"],
                "on_value": w.get("on_value"),
                # acroform_dump.py writes the /TU tooltip under "tu" (fresh-eyes
                # PR finding, bd cqc6: reading "tooltip" left the signal dead).
                "tooltip": w.get("tu") or "",
                "page": rect.get("page"),
                "x": rect.get("x"),
                "y": rect.get("y"),
            })
    return out


def _common_prefix(strings: list[str]) -> str:
    if not strings or any(not s for s in strings):
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def _aligned(values: list[Optional[float]]) -> bool:
    vals = [v for v in values if v is not None]
    return len(vals) >= 2 and max(vals) - min(vals) <= _ALIGN_TOL


def _signals_for(members: list[dict], base_signal: str) -> list[str]:
    signals = [base_signal]
    on_values = [m["on_value"] for m in members]
    if all(v is not None for v in on_values):
        if len(set(on_values)) == 1:
            signals.append(f"shared-on-value ({on_values[0]!r})")
        elif len(set(on_values)) == len(on_values):
            signals.append("distinct-on-values (radio-kid pattern)")
    if _aligned([m["x"] for m in members]):
        signals.append("column-aligned")
    elif _aligned([m["y"] for m in members]):
        signals.append("row-aligned")
    tip_prefix = _common_prefix([m["tooltip"] for m in members])
    if len(tip_prefix) >= 8:
        signals.append(f"tooltip-prefix ({tip_prefix[:40]!r})")
    return signals


def find_group_candidates(dump: dict) -> list[dict[str, Any]]:
    """Mine the dump for widget families that look like one logical question.

    Returns candidates as {"widgets": [full names], "leaves": [leaf[n]...],
    "signals": [...]}, ordered by first widget appearance. Suggestions only --
    adoption is the LLM's call (it can read the printed labels; we cannot).
    """
    widgets = _button_widgets(dump)
    candidates: list[dict[str, Any]] = []
    claimed: set = set()

    # Family A: same leaf base, multiple [n] indexes.
    by_leaf: dict[tuple, list[dict]] = {}
    for w in widgets:
        by_leaf.setdefault((w["page"], w["leaf"]), []).append(w)
    for (_, leaf), members in by_leaf.items():
        indexes = {m["index"] for m in members}
        if len(members) >= 2 and len(indexes) == len(members):
            members.sort(key=lambda m: (m["index"] if m["index"] is not None else 0))
            candidates.append({
                "widgets": [m["name"] for m in members],
                "leaves": [f"{m['leaf']}[{m['index']}]" for m in members],
                "signals": _signals_for(members, "same-leaf-multi-index"),
            })
            claimed.update(m["name"] for m in members)

    # Family B: single-index widgets whose leaf bases differ only by a
    # trailing number -- consecutive runs sharing page + column + on-value.
    remaining = [w for w in widgets if w["name"] not in claimed]
    by_prefix: dict[tuple, list[tuple[int, dict]]] = {}
    for w in remaining:
        m = re.match(r"^(.*?)(\d+)$", w["leaf"])
        if not m:
            continue
        by_prefix.setdefault((w["page"], m.group(1)), []).append((int(m.group(2)), w))
    for (_, _prefix), numbered in by_prefix.items():
        if len(numbered) < 2:
            continue
        numbered.sort(key=lambda t: t[0])
        # Split into runs: consecutive numbers + same column + same on-value.
        run: list[tuple[int, dict]] = [numbered[0]]
        runs: list[list[tuple[int, dict]]] = []
        for prev, cur in zip(numbered, numbered[1:]):
            same_col = (
                prev[1]["x"] is not None and cur[1]["x"] is not None
                and abs(prev[1]["x"] - cur[1]["x"]) <= _ALIGN_TOL
            )
            if (cur[0] - prev[0] <= _MAX_NUM_GAP and same_col
                    and cur[1]["on_value"] == prev[1]["on_value"]):
                run.append(cur)
            else:
                runs.append(run)
                run = [cur]
        runs.append(run)
        for run in runs:
            if len(run) < 2:
                continue
            members = [w for _, w in run]
            candidates.append({
                "widgets": [m["name"] for m in members],
                "leaves": [f"{m['leaf']}[{m['index']}]" if m["index"] is not None
                           else m["leaf"] for m in members],
                "signals": _signals_for(members, "numbered-leaf-run"),
            })

    # Stable order: by first widget's appearance in the dump.
    order = {w["name"]: i for i, w in enumerate(widgets)}
    candidates.sort(key=lambda c: order.get(c["widgets"][0], 1 << 30))
    return candidates


def render_candidates_block(candidates: list[dict[str, Any]]) -> str:
    """The labeled prompt block. Suggest, don't decide."""
    if not candidates:
        return ""
    L = [
        "GROUP CANDIDATES (deterministic suggestions -- NOT decisions)",
        "",
        "The widget families below were mined structurally from the AcroForm "
        "layer (shared leaf names, numeric runs, on-values, geometry). Each "
        "LOOKS like one logical question whose boxes belong together. For "
        "EACH candidate, decide from the PRINTED LABELS you can read:",
        "  - ADOPT it as ONE logical field (a radio or multi-checkbox group "
        "whose options each carry their own widget's pdf_field_name), or",
        "  - SPLIT it into separate fields when the boxes are genuinely "
        "independent questions.",
        "State your reason for each adopt/split decision in your reasoning "
        "BEFORE emitting the JSON (one line per candidate). Never drop a "
        "widget: every box listed here must appear in the schema, either as "
        "an option of the adopted group or as its own field.",
        "",
    ]
    for i, c in enumerate(candidates, 1):
        L.append(f"candidate {i}: {', '.join(c['leaves'])}")
        L.append(f"  signals: {'; '.join(c['signals'])}")
        L.append(f"  widgets: {', '.join(c['widgets'])}")
    return "\n".join(L)
