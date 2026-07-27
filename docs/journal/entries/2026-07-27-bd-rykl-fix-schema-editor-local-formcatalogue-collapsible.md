---
date: 2026-07-27
bead: polyglot-pdf-rykl
title: "fix(schema-editor): local FormCatalogue -- collapsible form cards to match hosted editor"
tags: [schema-editor]
---

## Trigger

The maintainer reported that the deployed schema editor
(`polyglot-editor-demo.web.app`) exposes a "Show/Hide form cards" control that
collapses the form-card grid, but the local editor (`localhost:3001`, launched
via `scripts/run-schema-editor.sh`) does not -- so locally the form cards stay
permanently expanded and eat roughly half the screen with no way to hide them,
making the editor hard to work with.

Root cause: the hosted and local front doors are two DIFFERENT components. The
hosted catalogue (`RemoteCatalogue`) got the collapse-to-dropdown + Show/Hide
toggle in bd `tynm`; the local catalogue (`FormCatalogue`) never received that
feature. It was not a stale build -- the control simply was never ported to the
local component.

## What shipped

Ported the bd-`tynm` collapse-to-dropdown pattern from `RemoteCatalogue` into
`FormCatalogue`:

- The card grid is now COLLAPSED by default behind a compact selector strip: a
  "Select a form" dropdown (listing every kit with its status + review %) plus a
  "Show form cards" / "Hide form cards" toggle. The full grid -- with its
  per-card Rename / Mark-complete / Run-extraction actions -- renders only when
  expanded, one click away. This matches the hosted editor's default footprint,
  giving the header's vertical space back to the editor.
- Two new pieces of state mirror the sibling: `expanded` (default `false`) and
  `actionKitId` (the strip's optimistic selection, reset when the parent
  confirms an open via the `selectedKitId` effect).
- A fresh folder open resets `expanded` to `false` (in `handlePickFolder`, after
  the picker resolves so a cancelled picker leaves the current state intact), so
  expanding folder A does not leave folder B expanded.

Scope decision (defended): I ported the dropdown + toggle only, NOT the hosted
strip's inline Rename/status/Run-extraction buttons. Criterion 2 requires those
actions be reachable in the expanded grid (they are), and duplicating the
extraction/instructions logic into the strip would have ballooned the diff for
no benefit to the reported problem. Both outer reviewers confirmed this as an
in-rubric, narrower-but-compliant port.

Verification: exercised the real dev build (worktree Vite server) with a mocked
directory -- confirmed the strip renders, the dropdown lists all forms
(`F1040 -- draft, 0%`, `I-90 -- complete, 0%`, `W7 -- draft (no schema yet)`),
and the toggle flips card count 0 -> 3 -> 0. Full schema-editor suite green
(774 tests); `tsc --noEmit` clean.

Assess (Step 5.5): rubric 3/3 PASS. Fresh-eyes ran Sonnet (diff 160+ lines ->
router picked sonnet; arm B active, `CLAUDE_CODE_SUBAGENT_MODEL` unset) ->
GAPS-FOUND (2), both nit-class. Fix/defer breakdown:
- FIXED inline: `expanded` not reset on folder change (a one-line
  `setExpanded(false)` + test).
- DEFERRED to bd `polyglot-pdf-yy1x`: the dropdown's optimistic `actionKitId`
  is not reverted when a parent open is declined (unsaved-changes confirm
  returns false). This is a faithful port of a pre-existing pattern that ALSO
  ships in `RemoteCatalogue`; a fix should touch both components, so it is out
  of scope for the faithful-port bead.
Final clearing round on Opus -> NO-GAPS.

Outer review (Step 5.6): review-worthy (executable frontend source). Two
independent clearing passes on the identical final diff, both NO-GAPS: primary
Opus + a second independent Sonnet (the second reviewer's model noted because a
2nd Opus was not spawned). Only findings were the already-deferred yy1x nit and
the benign in-rubric strip-asymmetry note above.

## Lessons

When a feature "exists in the deployed app but not locally," check first whether
the two surfaces are the SAME component or SIBLINGS. Here the hosted
(`RemoteCatalogue`) and local (`FormCatalogue`) catalogues are deliberate
siblings (the local one is bound to the File System Access directory API), so a
feature added to one does not reach the other -- it was a missing port, not a
stale branch or a build/deploy gap. Repo-specific enough that it stays in this
journal entry rather than a standards doc.

## Doc freshness

`check_doc_freshness.py` reported many STALE docs, but every one tracks
`backend/...`, `frontend/src/...`, or `docs/...` files that THIS branch did not
touch (they went stale from other recent backend/frontend commits, e.g.
`.github/workflows/ci.yml` on 2026-07-22 for `testing.md`). Per the freshness
rule, a stale doc is only mine to bump if its `**Tracks:**` globs cover a file
this branch changed. This branch changed only
`schema-editor/src/components/FormCatalogue.{tsx,test.tsx}`, which no stale doc
tracks -- so all were reviewed and left as pre-existing/unrelated. No
component/standards doc references FormCatalogue's grid-visibility behavior
(grep confirmed), so none needed a content update for this change.

## Files touched

- `schema-editor/src/components/FormCatalogue.tsx` -- added `expanded` +
  `actionKitId` state, the compact selector strip (dropdown + Show/Hide toggle),
  gated the card grid behind `expanded`, and reset `expanded` on folder change.
- `schema-editor/src/components/FormCatalogue.test.tsx` -- added an
  `expandCards()` helper and updated existing card-content tests to expand
  first; added four new tests (collapsed default, dropdown lists/switches,
  toggle expand/collapse, collapse-on-folder-change).
- `docs/journal/entries/2026-07-27-bd-rykl-fix-schema-editor-local-formcatalogue-collapsible.md`
  -- this entry.
