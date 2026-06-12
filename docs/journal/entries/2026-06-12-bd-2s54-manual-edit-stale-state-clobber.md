---
date: 2026-06-12
bead: polyglot-pdf-2s54
title: "Manual field edit clobbered all AI-filled values + confirmations (stale closure state)"
tags: [hotfix, postmortem]
---

## Trigger

Maintainer live-demo report (2026-06-11): manually editing one field made
every OTHER field's value and AI-confirmation checkmark disappear; the values
came back the next time Gemini sent a message. Filed as polyglot-pdf-2s54 (P1).

## What shipped

A two-site fix in `frontend/src/shared/connection.ts`. The original bead
hypothesis (React re-render destroying DOM-injected badges) was REVISED by the
implementing agent: the real mechanism was a stale-state clobber.

`createConnectionManager` holds a closure variable `state`, initialised once
from `SchemaFormStateManager.load()` at connection-create time and only
refreshed by `Object.assign` inside `onManualEdit` itself. Meanwhile every AI
fill goes through `WebFormConnection.updateField` -> its OWN `this.state` copy
-> `SchemaFormStateManager.updateField` -> sessionStorage. The closure never
sees those fills. On a manual-edit blur, `onManualEdit` merged the edit into
the stale closure state and saved -- overwriting sessionStorage with a state
missing every AI fill since connect. SchemaForm's `schemaFormStateChange`
listener then re-rendered from the clobbered state (values + `confirmed`
flags gone). Values "came back" because Gemini's next tool call re-saved
`WebFormConnection`'s intact copy.

Fix: both `onManualEdit` sites now re-load the persisted state
(`SchemaFormStateManager.load() || state`) before merging the edit, so the
edit lands on top of the authoritative state. Also added the previously
omitted `confirmationMethod: 'manual_edit'` at both sites.

Fresh-eyes triage breakdown: recorded in the PR merge ping (assess loop run
pre-PR per closeout Step 5.5).

## Lessons

Two independent in-memory copies of sessionStorage-backed state
(`connection.ts` closure + `WebFormConnection.this.state`) with last-writer-
wins save() is the root hazard; this fix heals the symptom site but the
dual-copy pattern remains. If it bites again, the fix is a single state owner
(or always load-before-merge at every save site).

## Doc freshness

`docs/standards/stateless-architecture.md` tracks `connection.ts` and was
flagged stale; reviewed and left -- this change fixes a bug in the documented
client-owns-state model rather than changing the model. All other flagged
docs track files this branch did not touch (worktree-creation mtime noise).

## Files touched

- frontend/src/shared/connection.ts -- load fresh state in both onManualEdit
  sites; add confirmationMethod 'manual_edit'.
- docs/journal/entries/2026-06-12-bd-2s54-manual-edit-stale-state-clobber.md
  -- this entry.
