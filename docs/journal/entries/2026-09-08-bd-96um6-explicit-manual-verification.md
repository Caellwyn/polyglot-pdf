---
date: 2026-09-08
bead: polyglot-pdf-96um6
title: "feat(forms): explicit manual verification -- Enter opens a verify modal"
tags: [testing, review, conventions]
---

## Trigger

Two merged PRs removed the accidental verification: typing used to write an audit
record, so tabbing through three fields wrote three
(bd `polyglot-pdf-uum5g`, `polyglot-pdf-gaxnf`).

That left a hole worth stating plainly: **until this bead there was NO keyboard
path to verification at all.** Verification came only from the verbal confirm or
the skip control, so a typing-only user could not finish a form. This is the
replacement gesture, and it is the half that makes the removal safe.

## What shipped

Five pieces. The first needed no code, which is why measuring first mattered.

**1. Un-verify on change** -- the maintainer's rule ("if a verified field is
changed, it should lose the verified status"). Probed before building: it ALREADY
holds, as a free consequence of `uum5g` writing `confirmed:false` unconditionally.
Pinned with tests rather than a redundant fix.

**2. Translations**, all 18 languages, with three DERIVED guards: the language set
equals `SPOKEN_LANGUAGES`, every language carries the full key set, and no value is
left as bare English -- the trap that once shipped a Tagalog label untranslated
while its neighbour was fine. Written as an ALLOWLIST of legitimate matches, not a
banned-word list.

**3. The modal.** Checkbox takes focus, so Enter-then-Enter or Enter-then-space
verifies; Escape or a click outside dismisses. Two decisions worth naming: it
**shows the value back**, because an audit claim should be about something the
user just looked at; and the tick **resets on reopen**, because a carried-over
tick would let one keystroke verify a field they never saw -- the same class of
bug this whole effort removes.

**4. The wire half.** Measured first, and it decided the design: a verify does NOT
reach the model on its own. The notify producer is a DOM change listener, and
verifying changes no input value.

| | notify calls |
|---|---|
| after a pure verify | 0 |
| after a real edit | 1 |

So the modal notifies explicitly. Per the maintainer -- *"we have an established
protocol... just set the state within that protocol"* -- there is no new message
type and no second producer: `manual_field_update` gained an optional `verified`
bool. The backend phrases both cases as STATE, retiring the last provenance leak:

- was: `User manually updated field 'X' with value: Y`
- now: `Field 'X' now holds: Y. It is verified.` / `...It is NOT verified -- read
  it back and ask the user to confirm it.`

Absent reads as false, which is the safe direction: an unverified field is
re-offered rather than treated as settled.

**5. The Enter wiring.** Bound above the view fork rather than threaded through
every field component, so Enter bubbles from either the schema form or the PDF
view. Scope is deliberately narrow: only a field holding a real value opens the
modal, because Enter otherwise reaches the form submit and advances the section,
and that is a shortcut people may rely on.

I first wrote here that "every field type renders `id={field.id}`, so one handler
covers all of them". **That was false, and it was the bug** -- radio and checkbox
groups render only `name`. The handler now resolves from id OR name, and
`SchemaForm.fieldIds.test.tsx` pins the id contract across every implemented type
by keying its cases on the `FieldType` union, so a new type that forgets it is a
compile error rather than a silent gap.

## Lessons

**A test of mine was vacuous, and only the mutation revealed it.** I asserted the
form submit did not fire, via an `onSubmit` spy. Removing `preventDefault` left it
GREEN -- because **jsdom does not implement implicit form submission**, so the spy
could never fire either way. It was testing nothing.

Rewritten to assert `evt.defaultPrevented`, which is the real observable contract,
and that version does redden. The only reason it surfaced is running the mutation
instead of trusting green -- see "Three of my tests proved nothing" below for the
full set, which this was the first of.

**Then I audited my own remaining absence assertions** rather than wait to be told.
Eight of them, which is the vulnerable shape. Two findings: the "modal does not
open" pair are anchored by positive counterparts (killing the modal reddens three
tests in the same file), and the one absence claim with no positive twin --
*"a dismiss must never verify"* -- I mutated directly. It reddens. That was worth
proving rather than assuming, because a dismissal that silently made an audit
claim would be the worst bug this feature could have.

**A correction I made to myself.** I claimed the React form had no notify path,
having grepped the `.tsx` files and found nothing. Wrong: `fieldManager` binds by
DOM **id**, not by surface, and React's inputs render that id -- so it covers both
surfaces. The grep looked like evidence of a gap and was evidence of nothing.

### What the reviews found, and the one pattern behind all of it

Thirteen inner rounds and six outer ones. Three findings were serious, and all
three were mine:

**Groups had no keyboard verification path at all.** Radio and checkbox-group
inputs render only `name`, never `id`, and the Enter handler keyed on `id`. That
is **30 of 323 fields** across the three shipped kits -- w7 `sex` and
`application_type`, i-90 `name_changed`, f1040 `filing_status` -- so a
keyboard-only user could not complete ANY shipped form. The exact hole this bead
exists to close, in a field class I had not enumerated.

**Fixing it broke voice fill.** Giving groups `id={field.id}` on option[0] made
`getElementById` succeed where it had always returned null, so `applyUpdates`
took the single-control path and a voice fill of a radio group **selected
nothing** while the model believed it had filled the field. Measured both
directions: `Female.checked` true without the id, false with.

**The worst was found on round ELEVEN: criterion 1 was never true.** The
criterion says "a second Enter OR SPACE verifies". Space only ticked the box --
and I had scored that criterion PASS eleven times, because my own test, titled
"SPACE ... ticks it, THEN THE CONFIRM BUTTON IS LIVE", recorded the broken
behaviour as correct. I wrote a test that documented the bug and read it as
coverage.

That one gesture then took FOUR implementations, three of which passed the entire
jsdom suite while being broken in a real browser:
  1. none -- space only ticked.
  2. requestAnimationFrame -- could fire the verify into an UNMOUNTED modal.
  3. keyup -- assumed the native toggle lands before keyup. I opened a real
     browser and measured: it does not.
  4. the checkbox's own CHANGE event -- correct by construction, with no ordering
     assumption left to be wrong about.
The probe that settled it also showed why no test here could: an automation
keypress does not trigger native activation at all (bd polyglot-pdf-u8xz9).

**The pattern, stated plainly: TWENTY-FIVE of my fixes closed one gap and opened or
exposed another**, several of them regressions against origin/dev -- working
behaviour I broke and a reviewer, not I, noticed. Every one has the same shape -- the change altered WHICH CODE
PATH a value takes, and I verified the path I was fixing rather than the paths I
was diverting. The id change alone touched five `getElementById` sites; I guarded
one, and the reviewers found the second, then the third.

What finally worked was enumerating the set before fixing (there are exactly two
resolution sites in `fieldManager.ts`, now behind ONE shared helper) and tracing
consumers BEFORE the review asks. That habit caught the notify payload sending
"verified and empty", the always-true harness clear-check, and the third alias
read -- none of which a reviewer had to find.

### Four kinds of bad test, all mine

Each was caught by running the mutation rather than trusting green:

1. An `onSubmit` spy asserting the form did not submit -- **jsdom does not
   implement implicit form submission**, so the spy could never fire either way.
2. A Cancel-button test that fired a keystroke AND a corroborating click, so it
   passed whether or not the guard existed. Written, ironically, in the commit
   closing out finding 1.
3. Non-first-option tests asserting only that the modal OPENS, when the claim is
   that it VERIFIES.

4. Source-reading GUARDS against the above. I wrote tests that grep the source
   to pin a rule, then **defeated them myself in one line**: appending
   `|| inputEl.type === 'checkbox'` to a membership test keeps the exact
   substring they search for while regressing the behaviour. They stayed green.

The lesson that generalises: **when jsdom is the environment, assert on the
event, not on what a browser would do next**; when a test asserts an absence, ask
what would have produced the presence; and above all, **test what the code DOES,
not what it LOOKS LIKE** -- every one of these four failures is the same mistake
at a different altitude. The grep guards were kept but demoted: they catch a rule
being DELETED, never one being WEAKENED, and the behaviour tests that call the
real exported functions are what actually protect it.

## Doc freshness

- `docs/standards/ws-protocol.md` -- the `manual_field_update` row documents the
  new `verified` key, its default, and why absent means unverified. Its citation
  was also still a line number that had drifted; re-anchored to the symbol, the
  same fix bd `polyglot-pdf-9bsnj` applied to its siblings.

## Files touched

- `frontend/src/schema-forms/components/VerifyFieldModal.tsx` / `.css` / `.test.tsx` -- new
- `frontend/src/schema-forms/components/verifyFieldTranslations.ts` / `.test.ts` -- new
- `frontend/src/schema-forms/components/SchemaForm.tsx` -- Enter handler + verify write
- `frontend/src/schema-forms/components/SchemaForm.verify.test.tsx` -- new, the gesture end to end
- `frontend/src/shared/connection.ts`, `frontend/src/webFormConnection.ts` -- the notify, exposed and carrying `verified`
- `backend/services/audio_handler.py`, `backend/services/form_filling_service.py`,
  `backend/routes/websocket_routes.py` -- the flag threaded through, and the state phrasing
- `backend/tests/unit/test_dti.py`, `frontend/src/shared/manualEditDoesNotVerify.test.ts` -- new pins
- `docs/standards/ws-protocol.md`
