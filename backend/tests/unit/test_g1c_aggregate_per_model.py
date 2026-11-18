"""bd polyglot-pdf-u0kcc: g1c_aggregate must never pool runs across MODELS.

probe_g1c_tuning.py gained --model; the aggregator globs every
g1c_precision_2026*.csv, so it must key on (model, prompt, size) and must
report every prompt arm present (incl. `prod`), or a multi-model artifact set
prints a blended number that looks like one arm.
"""

from __future__ import annotations

import csv
import sys
import types

import backend.scripts.g1c_aggregate as agg

_FIELDS = ["model", "prompt", "size", "case_id", "is_contradiction", "detected",
           "n_flagged", "error", "corpus_fp"]


def _write(path, model, prompt, detected):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        for i in range(4):
            w.writerow({"model": model, "prompt": prompt, "size": "20",
                        "case_id": f"c{i}", "is_contradiction": "1",
                        "detected": "1" if detected else "0", "n_flagged": "1",
                        "error": "", "corpus_fp": "FP"})


def test_runs_are_reported_per_model_and_prod_arm_kept(tmp_path, monkeypatch, capsys):
    _write(tmp_path / "g1c_precision_20261117T000001.csv", "model-a", "prod", True)
    _write(tmp_path / "g1c_precision_20261117T000002.csv", "model-b", "prod", False)
    monkeypatch.setattr(agg, "_DATA", str(tmp_path))
    # The corpus fingerprint reads a form kit; stub it (no kit is tracked).
    monkeypatch.setitem(sys.modules, "backend.scripts.g1b_corpus",
                        types.SimpleNamespace(corpus_fingerprint=lambda: "FP"))
    agg._precision()
    rows = [line.split() for line in capsys.readouterr().out.splitlines()
            if line.startswith("model-")]
    by_model = {r[0]: r for r in rows}
    assert set(by_model) == {"model-a", "model-b"}, rows
    assert by_model["model-a"][1] == "prod" and by_model["model-a"][4] == "1.000"
    assert by_model["model-b"][4] == "0.000"
