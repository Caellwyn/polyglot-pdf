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

**5. The Enter wiring.** Bound at the `<form>`, not threaded through every field
component -- Enter bubbles and every field type renders `id={field.id}`, so one
handler covers all of them. Scope is deliberately narrow: only a field holding a
real value opens the modal, because Enter currently reaches the form submit and
advances the section, and that is a shortcut people may rely on.

## Lessons

**A test of mine was vacuous, and only the mutation revealed it.** I asserted the
form submit did not fire, via an `onSubmit` spy. Removing `preventDefault` left it
GREEN -- because **jsdom does not implement implicit form submission**, so the spy
could never fire either way. It was testing nothing.

Rewritten to assert `evt.defaultPrevented`, which is the real observable contract,
and that version does redden. This is the fourth time in this line of work that a
test looked verified and was not, and the only reason it surfaced is running the
mutation instead of trusting green.

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
