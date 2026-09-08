---
date: 2026-09-08
bead: polyglot-pdf-uum5g
title: "fix(forms): typing must not silently verify a field"
tags: [testing, review, refactor]
---

## Trigger

"Verified" is load-bearing in this product's audit record: the firm reviews a
draft and the applicant undertakes review
([confirmation-and-audit.md](../../standards/confirmation-and-audit.md)). It was
being produced by a keystroke nobody means as an assertion -- **tabbing through
three fields wrote three audit records.**

Split out of bd `polyglot-pdf-96um6`, which was two separable halves: REMOVE the
accidental verification (this bead) and ADD the deliberate gesture that replaces
it (96um6, now blocked on this). The removal stands alone because its own
dependency, bd `polyglot-pdf-a08po`, already shipped the re-offer path -- so the
moment typing stops verifying, unverified fields are picked up by the existing
next-field search, and the verbal confirm and skip control still work. No window
where the form is unusable.

## What shipped

**The bead's premise was wrong, and measuring it is what caught that.** It cited
`connection.ts:368` "blur auto-confirms". The line had drifted to `:419`, but the
substantive correction is that in the REACT form **blur does not confirm at all**
-- it only validates. What confirms there is `handleFieldChange`, on EVERY
KEYSTROKE. Probed against the real component before writing any fix: typing
"Maria" with no blur and no Tab already stored
`{"value":"Maria","confirmed":true,"confirmationMethod":"manual_edit"}`.

So "blur stops confirming" as literally written would have fixed ONE surface and
left the main one -- the schema form AND the PDF-view popover, which share that
handler -- still auto-verifying.

Changed, together:

| Site | Trigger |
|---|---|
| `connection.ts` onManualEdit (initial) | vanilla-DOM `blur` AND `change` |
| `connection.ts` onManualEdit (**reconnect**) | the duplicate I nearly shipped |
| `SchemaForm.tsx` handleFieldChange | every keystroke; PDF popover routes here |

**One rule for every field type** (maintainer decision): no carve-out for
checkbox/select even though their `change` fires on a deliberate click.
Exempting them would give the form two verification rules and still let a stray
click write an audit record.

The VALUE is still stored -- only the verification is withheld.

**Review triage:** no adopt/reject/defer breakdown to report beyond the loops
themselves; the findings below were all my own, caught by sweeping and probing
rather than by a reviewer. Two stale in-progress beads (`0dsv4`, `ub7om`) that
prep flagged are the maintainer's own work from other sessions, unrelated to this
branch -- annotated rather than transitioned, since guessing at their real state
would overwrite someone else's work-in-progress on the strength of a timestamp.

## Lessons

**The duplicate closure I nearly shipped.** Sweeping for other consumers of "a
manual edit implies confirmed", I found `connection.ts` has TWO `onManualEdit`
closures -- the second on the RECONNECT path, with a comment saying the two "must
stay in step". I had fixed one. Typing would have silently started verifying
again after any reconnection.

This is scar #8's exact shape, and it is the third bead running where the first
fix was correct but was not the whole set. The guard now pins the SET: it
enumerates every `onManualEdit` closure from the source, asserts there are exactly
two, and checks each one. Mutation-verified against the case that matters --
regressing ONLY the reconnect closure, which a single-site guard passes.

**A test that supplies what production should supply.** My first mirror of
production's write hard-coded `confirmed: false` itself, so it would have passed
even if the real site still said `true`. Fixed with a source-reading drift guard.
Same family as the three occurrences in bd `polyglot-pdf-wurj8`.

**Three of my own mistakes, all caught by measuring rather than reasoning:**

1. I made the `copy_to` fan-out unverified too. Measured, that is inert -- the
   write chokepoint stamps the target regardless -- and the stamp is CORRECT: a
   copy target is `read_only`, so an unverified one strands `computeNextField` on
   a field nobody can act on. Comment corrected rather than leaving a claim the
   code does not honour.
2. Scoring the rubric surfaced a half I had never tested: criterion 2 also
   requires the verbal confirm and skip control to still verify. If those had
   broken, the form would be **unfinishable** -- worse than the bug being fixed.
3. My first version of that test asserted the wrong variable (after a manual edit
   the search deliberately resumes AFTER the edited field, so it would have
   passed regardless of verification), and the corrected version then failed on
   leaked `sessionStorage` state between `describe` blocks, which would have made
   the tests order-dependent.

**And a mutation that did not apply.** My first attempt to break `confirmField`
missed its target; the assert caught it. The green run it produced proved
nothing, which is precisely why the assert is there (scar #9).

## Doc freshness

- `docs/components/schema-forms.md` -- rewritten: it stated the auto-confirm rule
  as current. Now states that typing does not verify, on both surfaces and for
  every field type, and records why the `copy_to` target keeps its inherited
  confirmation.
- `docs/standards/confirmation-and-audit.md` -- `manual` clarified to mean typed
  **and** explicitly verified, plus a note that this backend enum is distinct
  from the client's `confirmationMethod`.
- Left stale deliberately: `auth`, `context-compression`, `jit-schema`,
  `pdf-filling`, `pdf-view`, `tool-call-flow` -- none tracks a file this branch
  touched. `voice-ai.md` does track `connection.ts`, but carries no claim about
  the manual-edit write path (checked, not assumed); its only related line is a
  pointer to the standard already corrected here.

## Files touched

- `frontend/src/shared/connection.ts` -- both onManualEdit closures
- `frontend/src/schema-forms/components/SchemaForm.tsx` -- the keystroke path
- `frontend/src/shared/manualEditDoesNotVerify.test.ts` -- new
- `frontend/src/schema-forms/components/SchemaForm.test.tsx` -- two tests that
  asserted the old contract, rewritten
- `frontend/src/schema-forms/components/SchemaForm.previewEdit.test.tsx` -- same
- `docs/components/schema-forms.md`, `docs/standards/confirmation-and-audit.md`
