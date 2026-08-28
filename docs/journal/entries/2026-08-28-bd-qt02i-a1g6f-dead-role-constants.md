---
date: 2026-08-28
bead: polyglot-pdf-qt02i, polyglot-pdf-a1g6f
title: "chore(editor): drop dead ROLE_EDITOR/ROLE_AUTHOR constants from editor_kit_routes.py"
tags: [editor, cleanup]
---

## Trigger

Two independent bead-catcher findings, both describing the exact same
defect: `backend/routes/editor_kit_routes.py` still declared
`ROLE_EDITOR`/`ROLE_AUTHOR` constants that bd `polyglot-pdf-hn0jq`'s
per-user-identity cutover left with no readers. The live copies moved to
`backend/services/editor_auth.py`, which `scripts/bootstrap_editor_user.py`
imports from directly.

## What shipped

Deleted the two dead lines and their header comment from
`editor_kit_routes.py`. Verified via repo-wide grep (`.py` files, excluding
`.venv`) that nothing imports or references
`editor_kit_routes.ROLE_EDITOR`/`ROLE_AUTHOR` -- the only surviving hits are
the live definitions in `editor_auth.py` and their consumers there. Full
backend suite green (4159 passed, 9 skipped) after the removal.

## Lessons

**Two beads filed hours apart, same file, same fix -- a quick `bd show` on
both before starting caught the duplicate and avoided doing the work
twice.** Nothing more subtle here: a routine dead-code cleanup that a
second bead-catcher pass re-found independently.

## Files touched

- `backend/routes/editor_kit_routes.py` -- dead `ROLE_EDITOR`/`ROLE_AUTHOR`
  constants and their comment removed.
