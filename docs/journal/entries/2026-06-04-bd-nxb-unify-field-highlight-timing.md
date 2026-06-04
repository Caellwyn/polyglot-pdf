---
date: 2026-06-04
bead: polyglot-pdf-nxb
title: "Unify field-highlight removal timing behind one constant"
tags: [refactor, conventions]
---

## Trigger

`bd polyglot-pdf-nxb` (triaged from TODO.md by `9np`): two different
field-highlight removal durations were confirmed live --
`webFormConnection.ts` used 1500ms (after an AI field confirm) and
`SchemaForm.tsx` used 2000ms (next-field hint). The bead asked to either unify
to one canonical value or document the two as intentional behind a shared named
constant; no magic numbers duplicated.

## What shipped

Unified both call sites to a single shared constant
`FIELD_HIGHLIGHT_DURATION_MS = 1500`
(`frontend/src/schema-forms/utils/fieldHighlight.ts`).

**Why 1500ms is canonical (grounded in the CSS, not arbitrary):** the
`.field-highlight` class runs the `highlight-pulse` animation in
`schema-forms/styles/schema-form.css`, which is `1.5s` long. The class is
removed after the pulse so the removal delay should equal the animation length.
The 2000ms site therefore left the class on for 500ms of dead time after the
pulse finished; 1500ms removes that. Pinning the constant to the animation
duration makes the CSS the single source of truth.

Both call sites (`webFormConnection.ts` AI field-confirm scroll, `SchemaForm.tsx`
next-field hint) now import the constant; the two magic numbers are gone. Audited
the rest of `frontend/src` -- these were the only two highlight-removal sites.

## Lessons

When two literals drift, prefer pinning the survivor to whatever *physically*
constrains it (here the CSS animation length) rather than picking the larger or
the more common value -- the constraint tells you which one was already correct.

## Doc freshness

No doc documents the highlight timing (checked `docs/components/schema-forms.md`
and `docs/components/websocket-routing.md`, the two docs that track these files),
so no doc update was needed. closeout_prep flagged ~13 docs stale, but every
flag was on BACKEND files (`websocket_routes.py`, `config.py`, etc.) that this
branch does NOT touch -- the staleness is pre-existing worktree mtime noise from
the prior tb7/zun work (since merged), unrelated to this frontend-only diff.
Reviewed and left as-is.

## Files touched

- `frontend/src/schema-forms/utils/fieldHighlight.ts` (new) -- the constant.
- `frontend/src/schema-forms/components/SchemaForm.tsx` -- 2000ms -> constant.
- `frontend/src/webFormConnection.ts` -- 1500ms -> constant.
