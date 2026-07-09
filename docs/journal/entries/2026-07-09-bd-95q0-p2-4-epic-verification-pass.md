---
date: 2026-07-09
bead: polyglot-pdf-95q0
title: "P2.4: epic verification pass (rubric execution + pdf-view.md update)"
sprint: 9
tags: [testing, review]
---

## Trigger

Final bead of the sprint-9 editable-Preview epic (`polyglot-pdf-oaiz`, plan
`docs/sprint_9_editable-preview_plan.md`), after P2.1 (PR #359), P2.2 (PR
#361), and P2.3 (PR #365) merged: execute the epic rubric end-to-end on the
local stack and bring `docs/components/pdf-view.md` to current state.

## What shipped

**Rubric execution.** The manual halves ran HEADLESSLY against the real
local stack (`scripts/dev-local.sh`: real backend on :8000 with a live
Gemini voice session, vite frontend on :5173) driven by Playwright -- the
Chrome MCP extension was unavailable, so the voice-harness's documented
Playwright pattern (bd 95uy) was reused via a scratchpad install; the
driver script + screenshots + JSON report live in the session scratchpad
and the evidence is recorded here and in the PR merge report.

| Row | Verdict | How verified |
|-----|---------|--------------|
| R1 option-rect painting | PASS (mechanism) | Vitest half: P2.2's FieldOverlay/valuePainting fixture tests. Manual: live app, i-90 ?previewUi=1, voice session CONNECTED; selecting an ethnicity option in its popover painted the X mark at that option's own mapped rect -- distinct from the field-level rect, screen position matching the schema rect times scale exactly (y 100.59 x 1.62 = 162.96px observed). See the data-bug note below. |
| R2 backfill coverage | PASS | P2.1 (PR #359): backfill_option_positions.py --check exits 0 with 0 unmatched on i-90/f1040/w7/w7-2; second run a no-op; pytest green. |
| R3 click-to-edit | PASS | Vitest half: P2.3's end-to-end interaction tests (incl. voice-advance dismissal, pinned). Manual: live voice session connected; clicked the A-Number field, typed in the popover -- the value repainted live into the printed comb field, sessionStorage stamped confirmed + manual_edit; Esc dismissed. The voice-advance dismissal also manifested live: a popover opened before the session's first next_field_hint settled was dismissed by that hint's currentFieldId change (the designed behavior, observed as the driver's first-run timing failure). |
| R4 show_if dimming | PASS | Vitest half: P2.2's PDFViewer dimming tests. Manual: real i-90 conditional -- p1_line5a_familyname (controlled by the name-change radio p1_checkbox4) rendered dimmed, then undimmed LIVE when the controlling option was selected via its own click-to-edit popover. |
| R5 flag-off parity + payload hygiene | PASS | pytest sanitizer assertions (P2.1); entry-chunk checks (P2.2/P2.3: zero pdf-view references, popover in the lazy chunk). Manual: a fresh flag-OFF session shows no toggle, no preview button, and ZERO pdf-view/pdfjs module requests (the same session flag-ON fetches 18). |

**Finding: i-90 ethnicity checkboxes are SWAPPED in the kit data** -- filed
as bd `polyglot-pdf-13vo` (P1). The R1 manual check painted the mark for
"Not Hispanic or Latino" inside the printed "Hispanic or Latino" box. The
painting is correct and WYSIWYG-faithful: the schema maps each ethnicity
option to the OTHER option's widget (the dump's own /TU tooltips prove
P3_checkbox6[0] is the Not-Hispanic widget), so the authoritative fill has
been ticking the opposite box all along. The preview surfaced a pre-existing
data bug on a legal form -- exactly the visual-QA purpose this epic was
built for. A negation-polarity sweep of all four kits' option labels vs
dump tooltips found no other instance (p2_checkbox2's hit was verified
pair-by-pair as a false positive).

**Docs.** `docs/components/pdf-view.md` was brought to current state
incrementally by P2.2/P2.3; this pass verified no stale "read-only /
phase 2" caveats remain in the doc and removed the one leftover in code
(`FieldOverlay.tsx`'s header still called the component READ-ONLY;
comment-only fix, bead surfaces updated accordingly).

## Lessons

- **The WYSIWYG preview is a data-QA instrument, not just UX.** Its first
  real exercise caught an invisible, user-facing fill bug (swapped ethnicity
  mapping) that every list-view and unit test had passed over -- the rects
  were "right" for the names claimed; only seeing the mark on the printed
  page exposed the wrong claim.
- **Timing around the voice session's first hint matters for UI drivers:**
  the first next_field_hint dismisses open popovers by design; drivers must
  let it settle before interacting (wait for the current-field marker).
- **The voice-harness Playwright pattern generalizes** to non-voice UI
  verification when the Chrome extension is unavailable: same entry flow,
  same fake-media flags, out-of-repo install per its RUNBOOK.

## Doc freshness

- `docs/components/pdf-view.md` -- verified current (P2.2/P2.3 updates);
  stamp bumped to this entry.
- All other docs flagged by the freshness gate track files this branch did
  not touch (stale before this branch); reviewed and left.

## Files touched

- docs/components/pdf-view.md -- stamp bump (content verified current)
- frontend/src/pdf-view/FieldOverlay.tsx -- stale READ-ONLY header comment
  replaced with the current three-capability summary (comment-only)
- docs/journal/entries/2026-07-09-bd-95q0-p2-4-epic-verification-pass.md
