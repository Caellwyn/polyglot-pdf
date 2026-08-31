---
date: 2026-08-31
bead: polyglot-pdf-kztlr
title: "fix(schema-editor): name kits the way the catalogue does, in every refusal"
tags: [schema-editor, ux, error-messages]
---

## Trigger

The maintainer, testing the deployed editor, hit a deletion refusal reading:

> Cannot verify whether "form-2" has confirmation records, so it will not be
> deleted.

There was no "form-2" anywhere on screen. The catalogue showed "W-7". The
message was about a real kit, correctly, and was nonetheless unusable -- it
named an identity the interface never displays.

Their words on the screenshot: *"it's not clear what the name is."*

## What the bug actually was

Not "the editor shows ids". The cards were already label-first: title
`{kit.label}`, id demoted to a muted subtitle. That part was right.

The bug was that MESSAGES named kits by id ALONE. A kit carries two identities
-- an `id` (a folder name, usually auto-generated: `form`, `form-2`) and a
`label` a human chose ("W-7"). Prose that mentions only the id cannot be matched
to any card, because the card leads with the other one.

This made a second bug worse. When deletion was still absolutely refusing (bd
`polyglot-pdf-6zhaf`), the refusal named `form-2`, so the maintainer could not
even tell WHICH form was refusing. Two defects compounded: an unclearable gate,
described unreadably.

## The fix

One formatter per side, used everywhere a kit is named in prose:

- `kitName()` -- `schema-editor/src/utils/kitName.ts`
- `_kit_name()` -- `backend/routes/editor_kit_routes.py`

Both return `"W-7" (form-2)` when a human chose the label, and plain
`"form-2"` when they did not.

That second case matters more than it looks. BOTH catalogues synthesise a
label from the id when metadata carries none (`form-2` -> "Form 2", via
`_friendly_label` / `friendlyLabel`), so an unlabelled kit does not arrive
label-less -- it arrives with a re-spelling of its own id. Naively showing both
would render `"Form 2" (form-2)`: one fact, printed twice, in the exact
situation where the human already has the least to go on. So the formatters
compare the two with separators and case flattened, and drop the label when it
adds nothing.

The distinction is narrow on purpose. `w7`'s real label is
"W-7 (ITIN Application)" -- it starts like the id but carries the form's
purpose, so it is NOT a restatement and both identities survive. An equality
test keeps that; a prefix test would have swallowed it, along with the id the
delete dialog requires the human to type.

## Enumerating the set, rather than fixing the instance

CLAUDE.md scar #8. The reported instance was the delete refusal -- already fixed
under bd `6zhaf`, whose code comment names this bead as the pending remainder.
Fixing only what was reported would have left every sibling to be found one
review round at a time.

So the set was derived mechanically, not recalled: an `ast` pass over the editor
route modules for every `HTTPException` whose `detail` interpolates a kit-id
name, and a balanced-paren scan of the frontend for every id-bearing string
reaching a user-facing sink. That found 16 backend refusals and 13 frontend
sites -- including two nobody would have listed by hand, which name a SECOND,
DIFFERENT kit (`superseded_kit`) that may not be on screen at all.

Two backend refusals keep a bare id, and both are correct:

- `_load_meta_or_404` "Unknown kit" -- the kit is not in the store, so there is
  no metadata to read a label from.
- `delete_editor_kit` "Kit not found" -- a delete race. The kit was there at the
  guard and gone at the write; naming it from the earlier metadata read would
  assert a label for something that no longer exists.

## Pinning the set, not the instances

`backend/tests/unit/test_kit_refusals_name_the_label.py` re-derives the same
`ast` enumeration at test time and requires every refusal to route through
`_kit_name`, with those two on a short allowlist keyed by
`(module, function, leading text)` -- not by line number, so ordinary edits
above them do not touch this file, but ADDING a bare-id refusal does.

A second test asserts every allowlist entry still matches a real refusal. An
allowlist that names nothing is the failure mode that matters: it silently
permits a future bare-id refusal that happens to land in the same function.

Verified by mutation, in both directions:

- Reverting ONE site to a bare id -> the guard fails and names the exact file,
  line and function.
- Adding a NEW bare-id refusal INSIDE an allowlisted function -> still caught,
  which is what proves the allowlist key is tight rather than function-wide.
- On the formatter itself: deleting the restatement check reddens 2 tests;
  weakening equality to a prefix match reddens the "label adds words" case.

One mutation initially failed to apply cleanly (line-ending mismatch produced
invalid syntax), and that run proves nothing -- it was redone with an
`ast.parse` check that the mutated file is still valid code before trusting any
result from it.

## What did NOT change

The cards. They were already right, and the bead's shape section left the
choice open ("either show the label wherever the id is currently shown, or show
both with the id clearly secondary"). The cards already do the second. Changing
them would have been churn, and the delete dialog makes the human TYPE the id --
so the subtitle is load-bearing, not decoration.

## What review found: my enumeration had the bug it was fixing

The fresh-eyes round found two sites I had missed, and they are worth recording
because they share one cause -- and it is the same cause as the original bug.

**The delete route.** The route the maintainer actually hit. My guard did not
flag it because the guard enumerated the NAMES an id could live under
(`kit_id`, `superseded_kit`, ...) and that route names its kit through a local
called `label`, assigned from `(meta or {}).get("label") or kit_id`. It had been
"fixed" under bd `6zhaf` to say the label -- which is better than an id, and
still not the rule this bead establishes: nothing makes labels unique, so a
label-only refusal is ambiguous in exactly the way an id-only one was, just
in the other direction.

**`writeLocalStatus`.** A thrown `Error` in `formKitDirectory.ts` that
surfaces through `FormCatalogue`'s error banner -- the same component whose
notices I had just converted, one function away, in a util module my
component-level scan never opened.

Both were invisible for the same reason: **I enumerated the shapes I had
already thought of.** That is the failure mode the guard existed to prevent,
reproduced inside the guard itself.

The fix was not to add two more names. It was to widen the vocabulary AND teach
the detector to follow an assignment -- a local assigned from `_kit_name(...)`
is correctly named, so flagging it would trade a blind spot for a false
positive. Widening without that would have made the guard noisy, and a noisy
guard gets suppressed, which is its own death.

A frontend counterpart (`kitNameCoverage.test.ts`) now scans util modules too,
scoped to kit entries specifically -- `field.id` is quoted the same way all
over the validation code, and flagging those would have made it unusable. Its
docstring states what it cannot see, because a guard that hides its limits
reads as broader assurance than it is.

Both fixes are mutation-verified against the reviewer's own findings rather
than against convenient synthetic cases: reverting the delete route to
label-only, and `writeLocalStatus` to a raw id, each reddens the guard that was
blind to it an hour earlier.

## Round 2: the guard was unsound, and one test passed by coincidence

Round 1's fix widened the detector's vocabulary and taught it to follow an
assignment. Round 2 showed that follow was **unsound**, and found a test that
had never actually tested anything.

**The detector marked a name safe forever.** It treated any local assigned from
`_kit_name(...)` *anywhere* in a function as correctly named *everywhere* in
it. So `label = _kit_name(kit_id, meta)` followed later by `label = kit_id`
would pass -- and `delete_editor_kit` uses exactly that assign-then-use shape,
so the hole sat on the route the bug was reported on. Now a name counts as safe
only if EVERY assignment to it is the safe one. Verified against the reviewer's
own proof-of-concept.

This is still flow-insensitive: it cannot reason about branches. That is
recorded in the code rather than left implied, and the bias is deliberate --
erring toward flagging is the safe direction for a guard, because a false
positive is a visible argument while a false negative ships.

**Six FormCatalogue tests passed by fixture coincidence.** They assert
`Extracted "w7"` on a kit whose id is `w7` and whose label is `W7`. Those
flatten to the same string, so `kitName` correctly emits the bare form -- which
is byte-identical to what the *unfixed* code emitted. Every one of them would
have passed a full revert. The sibling RemoteCatalogue tests were updated in
round 1 and do pin the real behaviour, so the two catalogues' suites had
silently diverged in what they proved.

Rather than churn the shared fixture, a new test drives the case that
distinguishes fixed from broken: id `form-2`, label `W-7` -- the maintainer's
actual situation. Reverting that file's notice reddens exactly one test, the
new one, which is the measurement that shows the other six were never load-
bearing.

**And an exemption that protected nothing.** The frontend scan excluded any
line containing `text-gray-500`, meaning to spare the card subtitle. But the
subtitle renders `{kit.id}` UNQUOTED and the pattern requires quotes, so it
never matched -- the carve-out was dead, and keyed on an unrelated Tailwind
class, so a future line pairing that class with a genuinely raw id would have
been waved through. Deleted. An exemption nothing needs is pure attack surface.

The through-line across all three rounds: every finding was in a **check**, not
in the shipped behaviour. The messages were right after round 1. What kept
being wrong was my confidence that they would stay right.

## Round 3: one more way to mutate a safe name, and the parity gap closed

Round 2 hardened the detector against REBINDING a safe name. Round 3 found the
same hazard through a different AST node: `label += f" ({kit_id})"` MUTATES the
name without rebinding it, so the walk never saw it. Not contrived -- this very
file builds messages with `+=` elsewhere.

The fix does not stop at `AugAssign`. Anything that binds a name in a way this
walk cannot classify -- a walrus, `with ... as`, `except ... as`, `global`,
`nonlocal` -- now marks the name unsafe. A guard should fail loudly on a shape
it does not understand rather than stay silent, and the cost of being wrong in
that direction is an argument, not a shipped bug.

**The parity gap, raised in rounds 1 and 2 and deferred both times, is now
closed.** The two formatters cannot share code across the language boundary, so
they share a CASE TABLE: the rows in `kitName.test.ts` are the rows in
`_PARITY_CASES`. Changing the rule on one side without the other reddens that
side. Writing the pin immediately found a real omission -- `kitName.ts` did not
name its backend counterpart anywhere, so a reader had no way to discover the
other half existed.

The parity check's own weakness is stated in its docstring: it cannot execute
the TypeScript from pytest, so it verifies the mirror exists and states the same
rule, and leaves behaviour to the shared table. A check that overstates itself
is the failure mode this whole bead kept rediscovering.

## Three rounds, one pattern

Every finding across all three rounds was in a CHECK, never in shipped
behaviour. Both exit criteria passed from round 1 onward. What kept being wrong
was the machinery meant to keep them passing:

| Round | The check's blind spot |
|-------|------------------------|
| 1 | Enumerated variable NAMES, so a kit named through a local called `label` was invisible -- on the very route the bug was reported on |
| 2 | Marked a name safe FOREVER after one safe assignment; six tests passed by fixture coincidence |
| 3 | Tracked rebinding but not MUTATION (`+=`) |

The lesson is not "write better guards." It is that a guard's claim is only as
good as the question it asks, and the question is easy to get subtly wrong in a
way no green run reveals. Each round's fix was correct and incomplete, which is
exactly the shape CLAUDE.md scar #8 describes -- experienced here from the
inside, in the checker rather than the code.
