---
date: 2026-08-28
bead: polyglot-pdf-6zhaf
title: "fix(editor): kit deletion is graduated, never a permanent block"
tags: [editor, safety, testing]
---

## Trigger

The maintainer tried to delete several forms in the deployed editor and could
not delete any of them -- including `form-2`, which has no extraction and was
never published. Every attempt returned the same refusal:

> Cannot verify whether "form-2" has confirmation records, so it will not be
> deleted.

Their read of it: "I don't want forms that are just permanently forever
undeletable... there are a lot of garbage forms in the form kit repo that are
just taking up space. I want to clean it up."

## What was actually wrong

Not the guard's logic -- the guard did exactly what it was written to do. The
problem was that its refusal had no way past it.

Diagnosed from the live logs rather than the error text, which mattered, because
the message pointed at the wrong thing:

```
confirmation_legacy_records_block_delete kit_id=form-2
editor_kit_delete_unverifiable error=confirmation records predating kit
  identity exist, so this kit cannot be cleared for deletion
```

Firestore holds confirmation records written before kits carried an identity
field. Nothing can attribute them to any kit, so `kit_has_confirmation_records`
raises `ConfirmationCheckUnavailable`, and the delete route turned that into a
409 with no override. Because those legacy rows are permanent, **every kit was
undeletable, forever, by anyone.**

Two things were checked and ruled out before landing on this, both of which the
message's wording invites you to suspect: the Firestore sink IS enabled on the
deployed service (`CONFIRMATION_FIRESTORE_ENABLED=true`), and the runtime
service account DOES hold `roles/datastore.user`. Neither was the cause.

**The message was the second bug.** It reads as a statement about `form-2`, so
the maintainer reasonably tried other forms, and then a form with no extraction
at all. The condition was global and had nothing to do with any named kit.

## The rule the maintainer set

Arrived at over three messages, and the middle one corrected my reading -- I had
taken "any unpublished form should be deletable" to mean *gate on publication
status instead of the confirmation check*, which is not what was meant. The
confirmation check is fine. The final rule:

> "it should be gate on publication AND confirmation. In fact, if a user has an
> agree history on it, it should be maybe double confirmed with huge warnings
> about the consequences."

So: graduated friction, scaled to what is actually at risk, with no permanent
block anywhere.

| Tier | Situation | What happens |
|---|---|---|
| A | never live, no records, check worked | deleted -- the junk-cleanup case |
| B | never live, but records exist OR check unavailable | one acknowledgement |
| C | ever live | double acknowledgement, explicit consequences |

A safeguard makes a destructive act **deliberate**, not **impossible**.

## What deletion actually destroys

The maintainer asked whether agreement records survive a delete. They do --
verified in `form_kits.py`, not assumed: `delete_kit` removes only the kit's own
prefix (schema, PDF, metadata, revision archives), while confirmation records
live in a separate Firestore collection it never touches.

But the implication is sharper than "nothing is lost". What a delete destroys is
**the evidence the record points at**. Afterwards the record still says "this
person confirmed these fields on revision X" while revision X is gone -- a claim
about a document nobody can produce.

That shaped the tier-C copy. Telling an author "this deletes their agreement
records" would be false, and false warnings train people to click through true
ones. The dialog says the accurate thing instead, and a test pins that wording.

## Scar tissue

**`status` is not the ever-live signal, and neither is `published_at`.** Both
were tempting and both are wrong alone, confirmed against the real demo store:

- `unpublished` means a RETIRED FORMERLY-LIVE revision (bd 6dz0), not "never
  published" -- so reading the reassuring word puts a form clients have seen on
  the LIGHT path.
- Kit `w7` is `status: complete` with **no** `published_at` (it predates the
  stamp), so keying on the timestamp classifies a live form as never-published.

Either signal is sufficient; neither is necessary. Surveying all seven kits in
the deployed bucket before writing the helper is what caught this -- reasoning
from the schema alone would have shipped one of the two halves.

**Unreadable metadata sorts to the STRICTEST tier**, not the most convenient
one. `_kit_was_ever_live(None)` returns True: an unparseable file is not
evidence of safety. Same fail-closed instinct as the original guard, but
escalating instead of blocking.

## What review caught

**A one-click delete of the wrong form -- worse than the bug being fixed.**
The warning state was cleared on a successful delete but not on Cancel, and
not when the dialog reopened for a different kit. A tier-B warning arms
"Delete anyway" immediately, so: get warned on kit A, cancel, open kit B,
and B's dialog opens one click from deleting a form whose id was never
typed. That defeats the type-to-confirm guard on precisely the action where
deleting the wrong row is the mistake that actually happens.

Fixed by clearing on a `deletePrompt?.id` effect rather than at each call
site -- every path that opens the dialog is covered instead of each one
remembering to. No test covered cross-kit reset; there is one now.

**"Double confirmation" the server never checked.** Both tiers gated on one
boolean, so `?acknowledged=true` cleared an ever-live delete exactly as it
cleared a never-live one. The second confirmation existed only in the
client's checkbox: any direct API call skipped it, and the server could not
record which level was actually given. One boolean cannot express two
levels. Now two distinct named tokens, and the weaker one does not escalate
into the stronger.

That one is worth remembering as a shape: I wrote a docstring claiming "the
client is required to double-confirm before sending it" -- which is not a
server contract at all, it is a hope about the client. If the enforcement
lives in the UI, the API does not have the property.

**The message relocated the bug instead of fixing it.** Tier B embedded the
raw exception text, which reads "...so THIS KIT cannot be cleared for
deletion" -- the exact per-kit phrasing that sent the maintainer through
every form in the catalogue, now nested in a parenthetical. The cause is
global, so the message says so, and the raw text goes to the LOG where an
operator debugging the sink actually needs it.

Also: `delete_kit`'s docstring still promised "a kit WITH records must never
reach this method", which my own change had made false -- and it is the
contract every store implementation reads.

**Round 2: absent metadata is not unreadable metadata.** `_kit_was_ever_live`
returned True for any non-dict, on the reasoning that an unparseable file is
not evidence of safety. Sound for a CORRUPT file; wrong for a MISSING one. A
kit with no metadata.json is a normal shipped state -- `form-kits/w9-heldout`
is a PDF and a note -- and it has manifestly never been published, because
there is no status to say so. So the junk-cleanup case this bead exists to
unblock got the scariest warning in the system: "This form has been
published, so clients may have filled it."

The codebase already knew the difference. `_stamp_readiness` distinguishes
absent from unparseable off the same filename set, for the same reason, a few
hundred lines up. I wrote a second, worse answer to a question that was
already answered -- and every fixture wrote a metadata.json, so nothing
caught it.

Both directions are pinned now, because over-correcting is the equal and
opposite bug: absent -> tier A, present-but-unparseable -> tier C. Mutating
either way reddens its own test.

Worth noting the blast radius honestly: all seven kits in the deployed store
carry metadata, so this would not have bitten the maintainer today. It was
reachable, not active.

## Verification

Eight mutations, eight caught. Four on the original design: dropping `unpublished`
from ever-live (a retired form deleted silently -- the log line in the failure
output shows it), ignoring `published_at`, ignoring the acknowledgement entirely
(the original bug restored), and letting the double-ack tick stop gating. Two on
the review fixes: restoring the cross-kit warning leak, and letting the weaker
acknowledgement clear an ever-live delete. Two on round 2's: treating absent
metadata as ever-live again, and over-correcting so a corrupt file took the
light path.
