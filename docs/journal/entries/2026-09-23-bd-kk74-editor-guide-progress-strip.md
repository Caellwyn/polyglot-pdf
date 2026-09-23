---
date: 2026-09-23
bead: polyglot-pdf-kk74
title: "EDITOR_GUIDE: the progress strip, and four stale beads closed without code"
tags: [conventions, review, schema-editor]
---

## Trigger

Bug-hunt continuation. Picked cross-surface bug beads from the store; most of
the session's value turned out to be in *triage* rather than in fixing, which
is itself the finding.

## What shipped

**bd `polyglot-pdf-kk74` -- EDITOR_GUIDE.md described a findings pane that no
longer renders.** The guide (stamped November 2025) told authors to read
"Validation errors" and "Reference warnings" from a bottom Validation Panel.
Sprint-18 C1 (bd `o7y9`) removed that list; the band is now a one-line progress
strip, and findings render at their fields. An author following the guide
hunted for a list that does not exist.

**The bead's premise needed correcting as part of the fix.** It says the panel
was "removed". The COMPONENT is still there -- `ValidationPanel.tsx` still owns
the lint round-trip, the Repair-all button, the limited-checking notices and the
refusal line. What was removed is the findings LIST inside it. Writing "the
panel was removed" would have replaced one wrong claim with another, so the
guide now describes the band by what it actually renders.

**Enumerating found seven stale sites, not the four cited.** The extra three
were the green/amber/red semantics the bead flagged as "worth fixing in the same
pass", plus a code snippet deriving overlay colour from `checkFieldComplete`
alone. Checked against `FieldOverlay.tsx`: colour comes from
`statusFromFindings`, which layers the human sign-off (bd `g63j`) over the
machine's opinion and lets a lint ERROR outrank both. The guide's snippet
described exactly the behaviour that component's own comment says was the bug it
fixed -- "letting the canvas paint green over a row the list showed flagged". So
the stale doc was not merely out of date; it documented a known defect as the
design.

Also corrected the ASCII diagram's count line (`89 complete, 43 review` ->
`89 reviewed . 43 to review . 132 total`, matching `ValidationPanel.tsx:530-586`).
Replacement strings were length-matched so the box-drawing alignment survives.

**Four beads closed with NO code change, each verified rather than assumed:**

- `u17i` (skip/confirm merge picks the unsafe direction), `5el4` (the merge
  resurrects a deleted `[]`-alias key) and `51lb` (switchToSection captures
  state before an await) all describe a spread merge
  `{...persisted, ...inMemory}` that no longer exists -- every refreshing
  handler now calls `reconcileFieldValues` (per-field, last-writer-wins on
  `lastModified`). The pinning tests each bead demanded already exist in
  `webFormConnection.statereconcile.test.ts`, driven through real handlers.
- `d95y` (legacy handshake sends no `kit_id`) -- `kit_id` now rides the legacy
  payload at `schemaFormState.ts:1221`.

## Lessons

**"Closed as stale" is a claim that needs the same evidence as a fix.** It
would have been quick to read `reconcileFieldValues`, see it is the right
shape, and close three beads. Instead I ran the mutation: replaced the
reconcile body with the exact `{...persisted, ...inMemory}` spread those beads
describe, and watched 6 of 15 tests in
`webFormConnection.statereconcile.test.ts` go red -- precisely the ones pinning
each bead's criteria. That is the difference between "the code looks right" and
"the protection is real and would catch a regression to the reported bug". A
green suite proves nothing on its own; a green suite that goes red under the
reported bug proves the bead is genuinely closed.

**A stale doc can document a known defect as the design.** The guide's colour
snippet was not vague or merely outdated -- it described `checkFieldComplete`-only
colouring, which is the precise behaviour `FieldOverlay.tsx` was changed to stop
doing, and whose comment explains why. A reader trusting the guide would have
reimplemented the bug. This is the strongest argument for the tier-1/2
current-state rule: the risk is not that a doc is unhelpful, it is that it is
confidently wrong in a way the code has already rejected.

**Read the code before trusting a bead's diagnosis, including its nouns.**
This bead said "removed"; the component was not removed, its contents were.
Both the bead and the fix would have been wrong in the same direction if I had
taken the word at face value. Beads are written by someone (often me) mid-review
with partial context, and the noun is as likely to drift as the line number.

## Doc freshness

- **`schema-editor/EDITOR_GUIDE.md`** -- the subject of this entry. Seven stale
  passages corrected; stamp bumped from November 5, 2025 to 2026-09-23.
- No tier-1/tier-2 docs under `docs/` were affected: this diff touches only the
  schema-editor's own guide and no source file, so nothing tracked by
  `check_doc_freshness.py` moved.

No CLAUDE.md changes.

## Files touched

- `schema-editor/EDITOR_GUIDE.md` -- progress-strip description, green-semantics
  corrections (4 sites), overlay-colour snippet, diagram label + count line,
  stamp.
