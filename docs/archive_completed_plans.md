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
