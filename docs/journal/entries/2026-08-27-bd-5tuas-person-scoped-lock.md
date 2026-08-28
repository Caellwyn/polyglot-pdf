---
date: 2026-08-27
bead: polyglot-pdf-5tuas
title: "feat(editor): the kit checkout lock names a person, not a role"
tags: [editor, review, testing]
---

## Trigger

The kit lock was ROLE-scoped because it had to be: with two shared secrets the
server could not tell two editors apart, so same-role contention was ALLOWED
rather than pretended about. Child 1 (`polyglot-pdf-hn0jq`) made the server
know WHO acted. This makes the lock know it.

## What shipped

The lock stores `{"role", "uid", "holder_label"}`. Editor B is refused a kit
editor A holds, and the refusal NAMES the holder. An author still preempts
anyone, including another author -- that IS the stale-lock release, and there
is no timer. Re-taking your OWN lock is not a steal.

`heldBy` stays a ROLE on the wire, on the maintainer's call: the editor
catalogue compares it to the literal strings "author"/"editor" at every site
that decides what the lock UI shows, including the check that gates the Release
button. `heldByLabel` carries the person additively, so the server names a
holder without breaking a frontend `polyglot-pdf-yswp3` owns.

## Scar tissue

**The migration case is the one a naive fix gets wrong.** A lock written before
this bead has no uid. Treating that unattributable holder as "somebody else"
would permanently refuse every editor on a kit nobody can be shown to hold,
with no way to clear it. Same-role contention falls back to the old ALLOW when
there is no uid -- pinned by its own test, because it is the behaviour a
reviewer would otherwise call a bug.

**A test I wrote to confirm my own fix passed under the mutation.** For the
author-takeover bug I asserted the kept lock does not name Dana -- but the BUG
keeps JOSH's uid verbatim, so it satisfied that too. The property is that a
transition by someone else ENDS the holder's turn, so the lock must be GONE.
An assertion written from the fix's shape describes the fix; an assertion
written from the property describes the requirement.

**My grep reported "all converted" from a check that could not see the thing.**
The supersede call spans two lines, so a single-line pattern missed it -- a
latent AttributeError that would have surfaced as a 500 AFTER the incoming kit
was already published. The replacement is an AST guard, and its own first
version had the same class of hole: it inspected positional arguments only, so
`actor=role.role` sailed through. Found by ACCIDENT, when a botched mutation
restore left exactly that form in the tree and the guard stayed green. All
three of my deliberate mutations had used the positional form, so they agreed
with the guard's blind spot and could not have found it.

**Five hand-lists failed in this epic before I stopped typing them.** The
helper set for that guard was the fifth; deriving it found a fourth helper I
had missed. A list you type is a claim about code you have not read.

**I defended an inert filter as load-bearing.** I argued a leading-underscore
check kept route handlers out of the derived set; route handlers are excluded
by their `Annotated[...]` being a Subscript, which the guard already tested.
Derived both ways: identical sets. It would have hidden a future PUBLIC helper
while looking like protection.

**Key ORDER was the only thing preventing a PII leak.** The lock stored the
holder's email under `"label"`, and `deploy-all.sh` greps metadata.json for
`"label"` with `head -1` to get a form's published DISPLAY NAME. A kit with no
top-level label publishes a contractor's email as the form's name in the
picker -- reproduced. Two coincidences were saving it (the lock is appended
last; no label-less kit exists today), and neither is a design. Renamed to
`holder_label`, which the grep cannot match at all.

**Six comments I wrote in this bead claimed properties the code did not have**
-- including one where I "corrected" a correctly-hedged `inert today` into a
false `LIVE now`. The pattern: write a claim while the code is fresh, the code
moves, the claim stays. Four of the six were text this bead ADDED.

## Deliberately deferred

`polyglot-pdf-g3oba`: the editor UI still says a lock was taken "from an
editor" and renders a Release button in the cell that now 409s -- `yswp3`'s
surface. `polyglot-pdf-0ygyv`: the deploy-side grep is still nesting-blind and
still bypasses `_safe_label`; unreachable at this HEAD after the rename, worth
hardening anyway. `polyglot-pdf-lphtd`: filed for the stale docs, then fixed
here instead, because CLAUDE.md sends the next agent to read one of them first.
