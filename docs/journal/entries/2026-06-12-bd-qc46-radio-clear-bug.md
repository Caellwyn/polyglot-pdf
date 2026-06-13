---
date: 2026-06-12
bead: polyglot-pdf-qc46
title: "Radio/checkbox clear with empty value now unchecks instead of selecting first option"
tags: [bugfix, frontend, fieldManager]
---

## Trigger

Fresh-eyes on PR #163 (w3ic/jbxm closeout) found that `handleRadioGroup`
in `fieldManager.ts` was selecting the FIRST radio when given an empty
string value. Root cause: `lowerRadioValue.includes('')` is `true` for every
string in JavaScript, so the fuzzy-match fallback matched the first option
immediately. The `handleSelect` clear guard (added in jbxm) had no equivalent
for radio or checkbox groups.

## What shipped

Added an explicit `newValue === ''` early-return guard to `handleRadioGroup`
that unchecks all inputs, dispatches change/input events, and returns -- skipping
the exact and fuzzy match loops entirely. Same guard added to `handleCheckboxGroup`
(`normalizedCheckbox.includes('')` has the same always-true trap, which would
have checked every box instead of clearing) and to `handleSingleRadio` (a clear
on a single radio found by id was silently ignored). The checkbox guard also
covers an all-empty / empty array (`['']`, `['', '']`, `[]`) -- the AI's
"no selection" shape. Mirrors the existing `handleSelect` empty-value branch.
New `fieldManager.clear.test.ts` pins all three shapes.

## Closeout notes

- Bundled with bd polyglot-pdf-z6xs (locked-field channel fix) -- both are small
  frontend bugs in the same fill-path surface.
- Doc-freshness flagged `docs/components/beads-remote-bootstrap.md` and
  `docs/components/pdf-filling.md` STALE, but only by wall-clock mtime of
  `bd_prime.py` / `pdfFiller.ts` -- neither file is in this PR's diff (this PR
  touches only `fieldManager.ts`, `webFormConnection.ts`, and their tests). No
  doc update needed.
