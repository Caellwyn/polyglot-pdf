---
date: 2026-07-11
bead: polyglot-pdf-ipw7
title: "computeNextField/progress/completion read field entries []-alias-aware"
sprint: 11
tags: [hotfix, testing]
---

## Trigger

Found during the jnjj.36 outer review (out of scope there): computeNextField's
main PRIORITY 1/2 loops read state.fieldValues[field.id] bare, with no
checkbox-group `[]`-alias fallback (bd 5k52 class), while resolveLivePin in
the same file already reads alias-aware. A group whose entry sits under the
bracket key variant reads as unfilled/unconfirmed and is re-offered forever.
Picked up as a sprint-11 rider while the epic's C2/C6 beads were
surface-blocked by parallel PRs (#403/#405).

## What shipped

Investigation first (the bead's either/or): post-5k52 every CURRENT write path
normalizes to the schema field id before writing (the AI-update handler
resolves the field object -- including the bracket fallback -- then keys by
field.id; manual UI edits key by field.id; confirm/skip write to the key the
alias-resolved entry lives under). The split state is therefore NOT reachable
through current writers, BUT it still arrives via legacy persisted
sessionStorage (a session that spans a deploy predating the normalization),
and the same file's resolveLivePin already treats the alias read as required.
Decision: apply the fix rather than a findings-only note.

readFieldEntryWithAlias now used at every field-entry read in
frontend/src/navigation.ts: both computeNextField priority loops, plus
getFormProgress and isFormComplete -- the latter two are the same bug class
with worse consequences (a required group confirmed under the alias would hold
isFormComplete false forever, blocking the form_complete validator trigger and
completion UX). Extending beyond the bead's named main-loop reads to the whole
file is the same one-line fix in service of the bead's "class" framing, noted
here rather than asked.

Three regression tests in navigation-confirmation.test.ts: confirmed-under-
alias group is NOT offered as next; a required alias-confirmed group completes
the form and counts in progress; the reverse split (unbracketed schema id,
bracketed entry key) also resolves.

## Lessons

- When one reader in a file is hardened against a state-shape hazard
  (resolveLivePin), every sibling reader of the same map should be audited in
  the same pass -- the split fix pattern invites exactly this drift.

## Doc freshness

None to bump (navigation internals have no tier-2 doc section affected;
the schema-forms doc's state description is untouched by an alias-read fix).

## Files touched

- frontend/src/navigation.ts (5 reads -> readFieldEntryWithAlias)
- frontend/src/__tests__/navigation-confirmation.test.ts (3 regression tests)
- docs/journal/entries/2026-07-11-bd-ipw7-navigation-alias-reads.md (this)
