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

### The review found the half I forgot: the model's own instructions

The client-side rule was right and both criteria passed -- but the **live system
instruction still told the model "Only the user's own manual edits are
auto-confirmed."** I changed what the client does and left the sentence that tells
the model what the client does.

That is worse than a stale comment: it is the one place the model is told anything
about manual edits, and it instructed the model to treat a typed field as done and
move on. The a08po re-offer path is a real safety net, but the fix is not to rely
on the model ignoring an explicit instruction.

The cross-surface pass found ONE such site. Enumerating found **four**:

| Site | Ships? |
|---|---|
| `DTI_SYSTEM_INSTRUCTION` | yes, the production default |
| `SYSTEM_INSTRUCTION` | only via `USE_DTI=false` (legacy path) |
| the `confirm_field` **tool schema** | yes, every session |
| the per-edit notify message | yes -- deliberately NOT changed |

The tool schema is the one I would most easily have missed and the one that
mattered most: its `confirmation_method` description said `manual: user edited
field` -- editing IS confirming, stated in the schema of the very tool that
records confirmations. Its ENUM is untouched (a wire contract); only the
human-readable description moved.

### And then the maintainer rejected my fix, correctly

My first correction replaced the false claim with a TRUE claim about typing ("a
value the user TYPED is not confirmed either -- read it back and confirm it").
That was still wrong, and the maintainer said why:

> "There's no reason for the model to even need to know if something was typed or
> previously spoken. Either the field is filled or not, and confirmed or not. [...]
> the state is the state however it was applied, and the model just needs to know
> the state and what to do about it."

That is the right model, and the mechanism already supports it: verification is
decided entirely client-side, and the re-offer is MECHANICAL -- `computeNextField`
hands the model a hint naming the unverified field whatever the model believes.
Probed: a typed-but-unverified field comes back as "next" with the model told
nothing at all. The model never had to reason about provenance; I had been adding
guidance for a judgement it does not make.

So all of it was DELETED rather than reworded -- including two older qualifiers
carrying the same defect: the DTI rule's "a field YOU FILLED is not confirmed"
and the legacy rule's "Fields filled by you (AI)". Both framed the rule around who
filled the field. Both now read simply: **a field is NOT confirmed until the user
explicitly agrees.**

**The net is a SAVING, not a cost:** measured against `origin/dev` by checking out
the base and importing its real config -- DTI 15303 -> 15200 chars, tool
description 143 -> 95, about **-38 tokens per session**. The shipped instruction
is smaller than before this bead. (Nothing pins SI size anyway: `test_dti.py`'s
size test asserts a SCALING PROPERTY -- DTI does not grow with section field count
-- not a budget.)

One provenance leak remains, deliberately: the notify message still says "User
manually updated field X". It is bd `polyglot-pdf-96um6`'s to rewrite as a STATE
statement, and the maintainer's model is recorded on that bead.

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

**The shape of this bead, worth naming.** The code change was small and correct.
Nearly every finding after it was **prose that outlived the code it described** --
two comments, two docstrings, two system instructions, a tool-schema description,
two docs. Those are exactly the artifacts nothing tests, and the reason each round
kept surfacing one more is that I fixed instances rather than sweeping for the set
until late.

The reusable rule: **when a behavioural rule changes, the code is the small part.
Grep for every statement of the OLD rule -- in comments, docstrings, model-facing
instructions, tool descriptions and docs -- and fix them as one set.**

### Two guards defeated, and the right answer was to stop guarding

Removing the false rule from the system instruction raised an obvious question:
what stops it coming back? Nothing pinned it -- which is exactly why my own
accidental deletion of the rule earlier had produced no red test.

The first guard was a **banned-words blacklist**. The cross-surface reviewer beat
it in one attempt with *"A value the user enters on screen counts as already
agreed"* -- semantically the exact carve-out, none of the banned words, three
tests green.

The second was a **generic carve-out-marker scan** (only / except / unless /
counts as / already agreed / auto-confirm) over a window around the rule. I
attacked it myself before the next review round and beat it on the first try with
*"Values the user supplies on screen are treated as settled on arrival"* -- a full
exemption, no markers.

**Two guards, two rephrasings, both defeated.** A third attempt would lose to a
fourth phrasing. That is the blacklist trap one level up, and the stopping rule is
to admit the tool cannot answer the question: a substring test sees PRESENCE,
never MEANING. This repo already measured that -- `test_dti_si_voice_rules.py`
records 163 substring assertions passing while the live model dropped a binding
obligation in 2 of 3 runs.

So the guard now pins only what it can: the rule is **present** (any live
phrasing, so an honest reword does not redden it), a confirm step is instructed,
and the confirm_field tool description -- a short, stable, genuinely enumerable
string, unlike 15k chars of prose -- carries no false claim. The semantic half is
routed to live validation, and the test says so in a comment so the next agent
does not re-attempt the blacklist.

## Doc freshness

- `docs/components/schema-forms.md` -- rewritten: it stated the auto-confirm rule
  as current. Now states that typing does not verify, on both surfaces and for
  every field type, and records why the `copy_to` target keeps its inherited
  confirmation.
- `docs/standards/confirmation-and-audit.md` -- `manual` clarified to mean typed
  **and** explicitly verified, plus a note that this backend enum is distinct
  from the client's `confirmationMethod`.
- `docs/components/pdf-view.md` -- claimed click-to-edit "stamps `confirmed` +
  `manual_edit`". Found by the cross-surface pass, NOT by the freshness checker:
  the checker keys on tracked-file globs, and this doc tracks only `pdf-view/*`,
  none of which this branch touched. A doc can be wrong about a file it does not
  track.
- Left stale deliberately: `auth`, `context-compression`, `jit-schema`,
  `pdf-filling`, `tool-call-flow` -- none tracks a file this branch touched.
  `voice-ai.md` does track `connection.ts`, but carries no claim about the
  manual-edit write path (checked, not assumed); its only related line is a
  pointer to the standard already corrected here.
- Repaired a stamp I had truncated in `confirmation-and-audit.md`: my helper
  replaced the LINE starting `*Last updated:`, but that stamp was a four-line
  sentence, so lines 2-4 survived as an orphan ending in a stray `.)*`. The
  freshness checker validates the DATE, never that the sentence closes. Recorded
  as bd memory `doc-stamps-can-span-multiple-lines`; the pdf-view stamp above was
  then written multi-line-aware.

## Files touched

- `frontend/src/shared/connection.ts` -- both onManualEdit closures
- `frontend/src/schema-forms/components/SchemaForm.tsx` -- the keystroke path
- `frontend/src/shared/manualEditDoesNotVerify.test.ts` -- new
- `frontend/src/schema-forms/components/SchemaForm.test.tsx` -- two tests that
  asserted the old contract, rewritten
- `frontend/src/schema-forms/components/SchemaForm.previewEdit.test.tsx` -- same
- `backend/config.py` -- BOTH system instructions (the shipping DTI one and the
  legacy `USE_DTI=false` path) still told the model manual edits are auto-confirmed
- `backend/services/form_filling_service.py`, `frontend/src/webFormConnection.ts`
  -- comments whose stated RATIONALE was the old rule; both behaviours unchanged
- `backend/tests/unit/test_dti.py` -- a docstring asserting the old rule as fact
- `docs/components/schema-forms.md`, `docs/components/pdf-view.md`,
  `docs/standards/confirmation-and-audit.md`
