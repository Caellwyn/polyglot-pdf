---
date: 2026-07-09
bead: polyglot-pdf-aw1u
title: "Paid i-90 re-extraction confirms the grouping fix end-to-end"
tags: [extraction, harness, verification]
---

## Trigger

Bead 3 (final) of the extractor-grouping fix: ONE paid Vertex re-extraction of
i-90 to confirm the qmxb fix (group-candidates default-ON + the
_complete_grouped_families safety net) actually produces the consolidated
select-one group on a REAL AI run -- not just on the offline synthetic tests.
The maintainer asked for this confirmation before relying on the fix for a
contractor onboarding new forms.

## What was run

One `extract_form.py` pass on `form-kits/i-90/form.pdf` via Vertex
`gemini-2.5-pro` (ADC), group-candidates now ON by default. The draft was scored
by the now-i-90-aware `eval_extraction` harness (bd ox6y).

## Result -- the grouping fix WORKS end-to-end

Eval row: `i-90  RED  lint 12/0  conv 0%  choice 100%  text 100%  fieldF1 98.5
structural PASS (5w, 1 group)`.

- **structural PASS (5w, 1 group)**: the P2_checkbox3 "reason for application
  (select only one)" group -- the exact bd 0nxh bug (extractor dropped 4 of 5) --
  came out FULLY CONSOLIDATED into ONE radio field (`p2_reason_for_application_b`,
  all 5 P2_checkbox3[0..4] widgets). The fix is confirmed on a real AI run.
- **group_completion: 0** in provenance: the LLM (with the group-candidates hint)
  consolidated the group ITSELF -- the deterministic safety net did not even need
  to fire. The hint alone solved the grouping; the safety net is the backstop.
- Extraction quality is high: 100% choice + text fill, 98.5 field-F1.

## What the paid run ALSO surfaced (out of scope -> filed)

The verdict is RED, but solely from an UNRELATED issue: the LLM emitted
`controls_fields` (the trigger-side conditional mechanism REMOVED at the P6.2 v2
flip) on 12 fields, which lint ERRORs as `legacy-trigger-side-logic`
(`schema_repair` deliberately does not convert it). This is independent of
grouping and blocks a CLEAN fresh extraction -- a real "fix the system" gap for
contractor onboarding. Filed as **bd polyglot-pdf-6s71** (auto-convert
controls_fields to show_if/require_if in repair, or reprompt the extractor).

## Verification / artifacts

The re-extracted draft is a transient extraction output (not committed -- it
carries no PII but is a scratch artifact). Its structural + fill scores are
recorded above. Reproduce: `extract_form.py --pdf form-kits/i-90/form.pdf --out
<tmp>` (Vertex ADC, ~a few min, paid) then `eval_extraction.py --form i-90
--draft <tmp>`.
