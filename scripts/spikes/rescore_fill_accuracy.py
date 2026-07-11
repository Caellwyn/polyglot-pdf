#!/usr/bin/env python3
"""Re-score a recorded run's fill accuracy against the CURRENT canon (bd jnjj.7).

The G3 meta.json stores every WRITTEN value (fill_accuracy.detail), so a run
can be re-scored offline when the expected-canon table changes -- without
re-spending live-Gemini money. Needed because the i-90 option-value vocabulary
migrated (widget ids -> semantic slugs, PR #333) between the 2026-07-06 DTI
runs and the 2026-07-11 baseline runs, so as-recorded accuracies from before a
canon fix are not comparable to after.

Usage:
    python scripts/spikes/rescore_fill_accuracy.py data/costs_i90_*.meta.json

Prints one line per meta: as-recorded vs re-scored accuracy + changed fields.
ASCII only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "mfsc", _HERE / "measure_form_session_costs.py")
_m = importlib.util.module_from_spec(_spec)
sys.modules["mfsc"] = _m
_spec.loader.exec_module(_m)


def rescore(meta_path: str) -> dict:
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    fa = meta.get("fill_accuracy")
    if not fa:
        return {"path": meta_path, "error": "no fill_accuracy in meta"}
    expected = _m.I90_EXPECTED
    matched = 0
    changed = []
    detail = fa.get("detail", [])
    for d in detail:
        fid = d["field_id"]
        written = d.get("written")
        exp = expected.get(fid)
        if exp is None:
            ok = written not in (None, "")
        elif exp == "":
            ok = _m._canon_value(written) == ""
        elif isinstance(exp, (list, tuple)):
            ok = _m._canon_value(written) in {_m._canon_value(e) for e in exp}
        else:
            ok = _m._canon_value(written) == _m._canon_value(exp)
        matched += 1 if ok else 0
        if bool(ok) != bool(d.get("ok")):
            changed.append(f"{fid}: {d.get('ok')}->{ok} (written {written!r})")
    total = len(detail)
    return {
        "path": meta_path,
        "as_recorded": fa.get("accuracy"),
        "rescored": round(matched / total, 4) if total else 0.0,
        "matched": matched, "total": total,
        "changed": changed,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    for p in argv:
        r = rescore(p)
        if "error" in r:
            print(f"{Path(p).name}: {r['error']}")
            continue
        print(f"{Path(p).name}: as-recorded {r['as_recorded']} -> rescored "
              f"{r['rescored']} ({r['matched']}/{r['total']})")
        for c in r["changed"]:
            print(f"    {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
