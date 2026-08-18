---
date: 2026-08-17
bead: polyglot-pdf-bdedm
title: "Suggest which form to retire -- and eleven rounds on whether the tests could tell"
sprint: 19
tags: [testing, conventions, review]
---

## Trigger

Sprint 19, epic polyglot-pdf-7jmy, the last child. bd polyglot-pdf-6dz0 had
already shipped the backend contract: `POST /kits/{id}/status` accepts
`replaces_kit_id` and retires that kit as part of a successful publish. It was
fully explicit -- the author had to already know which kit was outgoing and
name it.

Maintainer decision, 2026-08-07, verbatim: *"The publish modal lists other live
kits it thinks are the same form and asks the author to tick which to retire.
System does the finding; the human makes the call."*

Auto-retire was explicitly NOT chosen, and the reason drives everything here:
the only same-form signals available are unreliable. `form_number` is
documented NOT unique -- a standard W-7 and a firm's own W-7 variant share one,
which is exactly the firm-tier case -- and the label is free text an author can
rename. **A wrong auto-guess would retire another firm's live form.**

## What shipped

`GET /api/editor/kits/{kit_id}/retire-candidates`, author-only, matching on
`form_number` first and exact normalised label second. Each candidate carries
kit id, label, form number, whichever revision marker it actually has
(`edition_date > author_version > published_at`), and WHY it matched -- because
a label guess deserves more suspicion than a declared number.

A single-select dialog (the wire contract takes ONE `replaces_kit_id`), nothing
pre-selected, with "Publish, keep both" as a first-class outcome rather than a
cancel. Zero candidates opens no dialog at all.

## The design tension, and where it landed

The label matcher is where the care went, and it moved twice.

My first version used plain containment. My own test caught it suggesting
"Client Intake Addendum B" as a candidate when publishing "Client Intake" -- a
different form in the same family. I tightened it to containment-with-slack.

Round 1 then showed that slack matched **ten real form pairs**: I-130/I-130A,
I-864/I-864A, I-864/I-864EZ, I-129/I-129F, I-131/I-131A, I-765/I-765V,
1040/1040-X, 1099/1099-MISC, W-8BEN/W-8BEN-E, 941/941-X. Several of those
variants are **supplements filed ALONGSIDE their base form**, so suggesting one
to retire the other could break a live filing. My docstring was self-refuting:
it rejected a long suffix as "a different form" while a real sibling's
distinguishing suffix is one character. And my test only sampled long suffixes,
so slack of 5, 6, 7 or 8 all passed -- the dimension was untested.

It is exact-match now. **A missed suggestion costs one manual retire; a wrong
one asks an author to retire a live form, possibly another firm's, possibly one
a pending filing depends on.** The `form_number` path carries the real matches;
the label rule is the fallback for kits declaring no number.

Round 4 then found the same harm arriving through a different door: when both
kits declare a number and the numbers DISAGREE, the code fell through to the
label branch, so an identical label overrode two different declarations. With
production data -- where every real kit declares a number -- I-130 suggested
retiring I-130A. A declared mismatch now decides, in both directions.

## Eleven rounds, 35 findings

The rubric passed from round 1. Nearly everything after was about whether the
tests could detect the code being wrong -- and most of it was my error, not the
feature's.

The findings that would have reached users:

- suggesting a retire of I-130A when publishing I-130 (twice, by two routes)
- **the dialog was never a modal** -- I invented `modal-backdrop`/`modal-card`,
  which exist in no stylesheet, so it rendered as an unstyled inline block.
  Ten tests passed because JSDOM applies no CSS.
- that phantom styling made a real bug reachable: with no overlay, the
  catalogue's Publish buttons behind the dialog were clickable, and clicking
  one replaced the pending prompt -- so an author could tick a candidate
  computed for a DIFFERENT kit.
- the 3-character label floor silently killed W-7, W-2, W-4, W-9 and I-9 (all
  normalise to two characters), so two identically-labelled W-7 kits produced
  NO candidate and an author would publish a second live W-7.
- exit criterion 2 was unmet: the version-prompt retry re-called publish with
  three arguments, dropping the ticked kit -- reachable exactly in the
  firm-tier case this bead targets, with no error shown.
- `disabled={busy}` on the dialog's Publish button was the SOLE guard against a
  second concurrent publish (`handleSetStatus` has no reentrancy check), and
  all four busy gates survived deletion.

## The durable lesson: a test that cannot fail

This bead produced the same failure shape **five times**, in five disguises:

1. a loop over a collection that was always empty
2. `queryAllByText` matching nothing, so the loop body never ran
3. a `.find()` returning `undefined`, used without an existence check
4. a fixture excluded by a NEIGHBOURING rule rather than the one under test
5. a group mutation reddening a test that only one member of the group covered

Every one passed. Every one read as coverage. The tell was always identical: a
mutation stayed green.

Four techniques came out of it, and they are the transferable part:

- **Mutate each guard INDIVIDUALLY.** Deleting four gates together reddened
  three tests, which looks like full coverage; only one-at-a-time found the
  survivor. A group mutation proves the SET is covered, never each member.
- **Assert existence before asserting a property.** `expect(btn).toBeTruthy()`
  before `expect(btn.disabled)` is what separates "the control is correct" from
  "the control was not found".
- **Count what a loop actually asserted.** A census (`expect(checked)
  .toBeGreaterThanOrEqual(n)`) makes a vacuous loop self-reporting.
- **A test for a rule must be refused BY that rule and no other.** Three
  fixtures were excluded by the depth check, the underscore guard, and a length
  floor -- each while claiming to test something else.

And one about my own process: **declaring convergence is not the same as having
converged.** I told round 10 that cosmetic residue should come back as
NO-GAPS. It came back with a live double-submit path on a metered operation.

## What the reviews cost, honestly

Eleven rounds is far more than a suggestion dialog warrants. The first four
earned their keep -- without them this ships suggesting authors retire
supplement forms, with a dialog that is not a modal and a label rule that
ignores W-7. The last several found progressively smaller residue: an
unlabelled render branch, a threshold that bound by equality, a comment
overstating coverage.

The honest summary is that **my verification was less reliable than the reviews
of it**, and the gap was always the same: I trusted a green suite instead of
mutating the specific rule.

## Cross-surface result

Clean. The contract I most expected to break -- `published_at` moving from
write-only to READ, becoming the last-resort marker a human reads when choosing
what to retire -- was traced to ground: exactly one writer, every other metadata
write preserves the key, no backfill exists, and both real published kits
predate the field entirely. They render no marker line rather than "Published
undefined", and both declare an `edition_date` so they never reach the fallback.

## Follow-ups filed

- bd polyglot-pdf-jsosq -- a kit declaring a form number vs one declaring none
  still falls to the label check.
- bd polyglot-pdf-m3geo -- the dialog omits the form number on a label match.
- bd polyglot-pdf-3abn3 / polyglot-pdf-9303d -- Delete, lock, Translate options
  and Refresh stay live behind EVERY modal in this catalogue (pre-existing;
  reproduces on origin/dev via the version dialog).
- bd polyglot-pdf-dkmxm -- the candidate lookup's fail-open is unpinned, and it
  is the only handler that swallows AuthError.
- bd polyglot-pdf-ezcc0 -- closed here: the route table row.
