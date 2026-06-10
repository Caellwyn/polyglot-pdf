---
date: 2026-06-10
bead: polyglot-pdf-fwac
title: "ASCII-clean the section-sign in harness_ledger.py docstrings"
tags: [chore, ascii]
---

## Trigger

A tiny ASCII-hygiene cleanup spotted while fixing the append-newline bug (cpx8)
and deliberately scoped out of that work, then surfaced as a background task chip.

## What shipped

Two pre-existing U+00A7 section-signs in `scripts/harness_ledger.py` module
docstrings (L5 and L379, "plan section Change #1") violated CLAUDE.md scar #6
(.py source must be ASCII-only -- a cp1252 hazard if a glyph reaches stdout).
Replaced both with the ASCII word "section". Docstring-only; no behavior change.

## Verification

- `open("scripts/harness_ledger.py", encoding="ascii").read()` raises nothing.
- `py_compile` clean.
- 34 `tests/test_harness_ledger.py` tests pass (docstring-only change).

## Notes

- Review-SKIPPED: the diff is comments/docstrings only -- it cannot introduce a
  runtime regression, so no Codex review per the closeout Step-6 gate.
- Doc-freshness flagged ~11 docs STALE; all false positives. This branch touches
  only `harness_ledger.py`, and NO tier-1/2 doc tracks that file -- every flag is
  mtime-noise from backend/frontend files this branch does not touch.
- The closeout-prep beads audit flagged the P1 epic `polyglot-pdf-hrn` as stale
  (in_progress > 1d). That epic is a long-running, still-active sprint-1 epic from
  other sessions (its own note documents the recurring false-positive); not
  touched or owned by this PR, left as-is.

Closes polyglot-pdf-fwac.
