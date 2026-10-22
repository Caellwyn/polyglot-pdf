---
date: 2026-10-22
bead: polyglot-pdf-k5dnc
title: "chore(deps): upgrade PyMuPDF 1.24 -> 1.28 with PDF-fill rendering verified"
tags: [testing]
---

## Trigger

Pinned back by bd niwcu. PyMuPDF is the PDF fill/render core; render fidelity is not unit-tested.

## What shipped

- Fill fidelity, end to end: the real /fill-pdf route filled the i-90_v2 kit (94 fields incl. comb, radio, checkbox, checkbox_group, select, textarea) under 1.24.14 and 1.28.2. All 195 widgets read back identically, all 20 checked boxes match by raw /AS, and all 7 pages render pixel-identical with either version as renderer.
- import fitz is deprecated from 1.26 and prints a warning at import -- a non-JSON line at every backend startup that fails tests/test_structlog_json_output.py. All 44 importers now use 'import pymupdf as fitz' (call sites unchanged); tests/test_no_deprecated_fitz_import.py pins the set (git ls-files discovery, mutation-verified, skips itself).
- 1.28 keeps a handle on a PDF it failed to open; on Windows the TemporaryDirectory cleanup then raised PermissionError and turned derive-divisions' 422 into a 500. Both TemporaryDirectory sites in editor_kit_routes.py pass ignore_cleanup_errors=True; pinned by the existing 422 test.
- Full suite: 6765 passed. Hold released.

## Lessons

A dependency's deprecation WARNING can be a behavior change when an invariant constrains output (JSON-only logs).

## Doc freshness

docs/components/pdf-filling.md names PyMuPDF but no version; README's version line -- see Files touched.

## Files touched

- backend/requirements.txt, backend/routes/editor_kit_routes.py, 44 importer files, tests/test_no_deprecated_fitz_import.py
- .github/dependabot.yml, tests/test_dependabot_config.py (hold released)
