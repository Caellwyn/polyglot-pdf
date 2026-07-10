---
date: 2026-07-09
bead: polyglot-pdf-lj5v
title: "DTI get_field_guidance option sanitization: share one helper with the JIT path"
tags: [voice-ai, dti, hipaa-pii-policy]
---

## Trigger

Fresh-eyes finding during bd polyglot-pdf-5f41 closeout, surfaced again in the
2026-07-09 bead audit. `manifest_service.get_field_guidance` (the DTI per-field
guidance builder) assigned raw option dicts straight into its returned dict:

```python
options = field.get("options") or field.get("allowed_values")
if options:
    guidance["options"] = options   # raw -- carries pdf plumbing
```

Schema option dicts carry PDF plumbing (`pdf_field_name`, `pdf_on_value`,
per-option `pdf_position` -- bd polyglot-pdf-5f41) plus `label_translations`. The
JIT sibling `get_next_field_schema` was hardened to strip options to
`value/label/spoken_label` (bd 5f41), but `get_field_guidance` -- the DTI path,
which is the shipped default -- was never given the same boundary. The two
parallel option builders applied inconsistent sanitization.

## Why it mattered (and why it wasn't a live leak)

No live leak today: `ai_context.render_field_guidance` only reads `value`/`label`
when rendering the guidance text block, so the extra keys were dropped before
reaching the model. But `get_field_guidance` returns a dict that feeds BOTH the
DTI system instruction (field 1) and the confirm_field tool response (fields
2..N). Any future consumer reading that dict directly -- a JSON tool response, a
log line -- would leak PDF-internal detail into a model-facing payload, violating
the sanitization boundary 5f41 established. This is a defense-in-depth /
consistency fix, not a live-incident fix.

## What shipped

- New module-level `_sanitize_options(options)` helper in
  `backend/services/manifest_service.py`: strips each option dict to
  `value/label/spoken_label` (via a shared `_MODEL_FACING_OPTION_KEYS` tuple),
  passes bare-string options through unchanged.
- `get_next_field_schema` now calls the helper (was an inline comprehension --
  identical behavior, now shared).
- `get_field_guidance` now calls the helper (the actual fix -- was raw).
- Tests: `test_get_field_guidance_strips_pdf_plumbing_from_options` (mirrors the
  JIT path's strip test + a belt-and-suspenders `json.dumps` assertion that no
  plumbing key survives anywhere in the payload) and
  `test_get_field_guidance_passes_bare_string_options_through`.

## Verification

`backend/tests/unit/test_manifest_service.py` 10/10 green; full backend suite 992
passed / 2 skipped / 3 deselected (`-m "not external"`). Pure internal refactor:
identical option output for every existing caller, one function's leak-surface
closed.

## Doc-freshness note

closeout_prep flagged ~17 tier-2 docs as stale, but all are pre-existing
(dated 2026-07-05..08, from other same-day backend edits). This change is a
self-contained internal refactor of one helper's option handling -- it alters no
documented contract (SI shape, wire format, validation-delegation), so no tier-2
doc describes behavior this changes. No doc update warranted; recording the review
here per the closeout doc-freshness protocol.

## Scar tissue

Two parallel builders of the same model-facing structure (JIT
`get_next_field_schema` vs DTI `get_field_guidance`) drifted: a sanitization
boundary added to one was silently absent from the other. When a security/PII
boundary exists in one of two sibling code paths, factor it into a shared helper
BOTH call, rather than duplicating -- otherwise the next builder inherits the
gap. Cross-ref bd polyglot-pdf-5f41 (the original JIT-path boundary).
