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
have checked every box instead of clearing). Mirrors the existing `handleSelect`
empty-value branch pattern.
