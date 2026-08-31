---
date: 2026-08-31
bead: polyglot-pdf-fejzd
title: "chore(notice-tts): remove duplicated GENERATED-FROM comment block"
tags: [backend, notice-tts]
---

## Trigger

`backend/services/notice_tts.py`'s `# GENERATED FROM
frontend/src/schema-forms/resumeStrings.ts` comment block (4 lines,
including the trailing blank `#`) appeared twice back to back above
`NOTICE_TEXT`, reading like a bad merge -- the claim ("Derived rather than
hand-written...") is correct only once.

## What shipped

Removed the duplicate copy, leaving exactly one instance. Pure comment
deletion -- verified `grep -c` for the block's first line now returns 1,
ran the full `test_notice_tts_parity.py` suite (48/48 pass, unaffected
since nothing but a comment changed).

## Files touched

- `backend/services/notice_tts.py` -- 4 duplicate comment lines removed.
