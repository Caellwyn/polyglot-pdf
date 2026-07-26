# Completed sprint plans

Record of sprint plans archived from repo root to [`archive/`](archive/) once
the sprint shipped (the sprint-archive protocol -- see
`scripts/check_doc_freshness.py` and CLAUDE.md sprint closeout). One row per
archived plan; the plan file itself is kept verbatim in `archive/` for history.

| Sprint | Plan | Scope | Epics / beads | Archived |
|--------|------|-------|---------------|----------|
| 2 | [`archive/sprint_2_spear-adoption_plan.md`](archive/sprint_2_spear-adoption_plan.md) | SPEAR partial adoption: epic-level planning, exit criteria, adversarial assess loop | epic `polyglot-pdf-7dkb` (closed) | 2026-07-05 (bd `polyglot-pdf-mpoe`) |
| 3 | [`archive/sprint_3_voice-roundtrip-reliability_plan.md`](archive/sprint_3_voice-roundtrip-reliability_plan.md) | Voice round-trip reliability: google-genai SDK cutover, model/VAD experiments, reconnect resume | epic `polyglot-pdf-1cnn` + beads `4sv7`/`vmxx`/`95uy` (all closed) | 2026-07-05 (bd `polyglot-pdf-mpoe`) |
| 4 | [`archive/sprint_4_sliding-window-context_plan.md`](archive/sprint_4_sliding-window-context_plan.md) | Sliding-window context management exploration: post-SDK-2.8 compression re-test, token-cost measurement, go/no-go | bead `polyglot-pdf-eycd` (closed); follow-on session-management work lives under epic `polyglot-pdf-l3a` | 2026-07-05 (bd `polyglot-pdf-mpoe`) |
| 9 | [`archive/sprint_9_editable-preview_plan.md`](archive/sprint_9_editable-preview_plan.md) | Editable Preview mode: click-to-edit popover, option-level `pdf_position` backfill + selection-mark painting, `show_if` dimming -- all behind `?previewUi=1` | epic `polyglot-pdf-oaiz` + beads `5f41`/`lp5v`/`7esr`/`95q0` (all closed; PRs #359/#361/#365 + the verification PR) | 2026-07-09 (bd `polyglot-pdf-95q0`) |
| 10 | [`archive/sprint_10_deterministic-divisions_plan.md`](archive/sprint_10_deterministic-divisions_plan.md) | Deterministic form divisions: sections derived by code from the PDF (widget-name conventions / printed-heading detection / page+cap fallback), aligned with the form's own printed sections, plus schema-editor section add/remove/merge and the shipped-kit retrofit | epic `polyglot-pdf-6cfu` + beads `6cfu.1`-`6cfu.6` (all closed; final retrofit PR #409) | 2026-07-12 (bd `polyglot-pdf-6cfu.6`) |
| 15 | [`archive/sprint_15_relationship-extraction_plan.md`](archive/sprint_15_relationship-extraction_plan.md) | Relationship extraction: the dual-role show_if/require_if clause in the production extraction prompt (W-7 require_if 0/9 -> 3-7/9), trigger-correctness + spurious metrics, and zero-silent-drops harvest of trigger-side edges (unlocks/hides convert; locks/makes_optional retained loud) | epic `polyglot-pdf-o2bs` + beads `eprg`/`dsbl`/`kfni`/`xbfm`/`urrt` (all closed; PRs #480/#482/#485/#487) | 2026-07-26 (bd `polyglot-pdf-2hg1`) |
