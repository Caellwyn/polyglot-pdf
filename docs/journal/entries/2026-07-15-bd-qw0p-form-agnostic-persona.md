---
date: 2026-07-15
bead: polyglot-pdf-qw0p
tags: [voice, system-instruction, dti, product-framing]
---

# Live-session prompts made form-type agnostic (polyglot-pdf-qw0p)

Follow-on to the README immigration-first reframe (bd polyglot-pdf-7d19, PR #444).
That PR flagged that the Gemini live-session system instructions still described
the assistant as a "medical-form assistant", contradicting the now form-agnostic
(immigration-first) product framing. Maintainer directive 2026-07-15: make it just
a "form filling assistant", form-type agnostic.

## Change

Three prose strings in `backend/config.py`:

- `SYSTEM_INSTRUCTION` (legacy full-SI, DEPRECATED-but-live fallback):
  `"Medical assistant: {form_title} ..."` header -> `"Form assistant: {form_title} ..."`.
- `DTI_SYSTEM_INSTRUCTION` (production):
  `"warm, empathetic medical-form assistant"` -> `"warm, empathetic form-filling assistant"`.
- DTI CONSTRAINTS empathy cue: `"this is a medical form"` ->
  `"forms can be stressful to fill out"` (keeps the empathy directive without a
  form-type; arguably truer for immigration/legal intake).

Plus `backend/scripts/probe_si_bisect_i9q8.py`: its `_full_minus_language` bisect
variant anchors on the literal `"Medical assistant:"` in the rendered legacy SI
via `str.find`; updated to `"Form assistant:"` so the historic probe still
resolves its anchor instead of raising.

## Why this was safe

The word "medical" appeared only in self-description / empathy prose -- no
conditional, tool name, option value, field-guidance key, telemetry field, or
cost/log parser branches on it. No test asserts on the persona strings. The
`DTI_SYSTEM_INSTRUCTION` stays brace-free (test_dti asserts zero placeholders) and
`SYSTEM_INSTRUCTION.format(...)` still succeeds. Both SIs remain ASCII (scar #6).
The probe's new `"Form assistant:"` anchor occurs exactly once in the rendered
legacy SI, so `str.find` is unambiguous.

## Verification

Full backend suite green (1082 passed, 2 skipped) at closeout prep. Both live SIs
verified to render with no "medical" wording; probe `_full_minus_language`
re-verified to resolve against the new text. Fresh-eyes assess loop NO-GAPS; two
independent Opus outer reviews both NO-GAPS.

## Left as-is

The `README.md` / `pitch/` use of "medical" in the general use-case sense (e.g.
"Medical Intake Forms" as use case #3) is product-description context, not the SI
persona, and stays. The historical journal entry for 7d19 still quotes the old
"medical-form assistant" string as the pre-fix state it described -- the journal is
the chronological record and is not rewritten.
