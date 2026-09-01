---
date: 2026-09-01
bead: polyglot-pdf-n5fwd
title: "feat(editor): hide kits out of the catalogue, and a search/status filter"
tags: [schema-editor, ux, catalogue]
---

## Trigger

Two maintainer ideas from 2026-08-28, filed as paired beads:

> another good idea would be to have the ability to archive the forms and
> remove them from the normal form selection view. Maybe some filter options or
> search options as well.

The demo store has accumulated junk kits (`form`, `form-2`, `form-3`, ...) that
nobody is working on, and they crowd out the real ones in both the card grid and
the selector strip. Deleting them is the destructive half (bd
`polyglot-pdf-6zhaf`, shipped); this is the reversible half.

Both beads say to plan them together, and they are right: **a shelf with no
filter to see what is on it is half a feature**, and the filter is the way back.
So they ship as one change.

## Two decisions that were the maintainer's

**Who may hide.** By the established tier line this looks editor-ish -- it is
reversible, spends no tokens and creates nothing, which is exactly where
`POST /label` sits. But hiding changes what OTHER people see. The maintainer
chose **author-only**. That is a narrower rule than the code would have
suggested, and it is theirs to set.

**What to call it.** The editor already uses "archive" for the per-kit revision
archive -- the frozen, read-only copy of a superseded version, created
automatically at publish, which a client's confirmation record points at as
proof of what they agreed to. Overloading that word for "put this out of my
sight" would have been the third meaning in one UI. The maintainer asked what
the existing archive actually does, then chose **Hide / Hidden**.

Worth recording that the question was worth asking: the bead itself proposed
"shelve", and the answer only became obvious once the existing meaning was on
the table.

## The shape

A separate `hidden` metadata key, **deliberately not a fifth lifecycle status**.
Status answers "where is this in its life?" and drags `_WRITE_LOCKED_STATUSES`
with it; hiding answers "do I want to look at this?" and has to stay orthogonal.
Making it a status would have pulled in the write-lock set, the `KitStatusBody`
literal, `_status_of`'s fallback, and the local reader's status ladder -- four
places that would then couple visibility to publication.

So there is **no write-lock gate**, matching `/label`: a `complete` or
`unpublished` kit can be hidden, and the revision an audit record names stays
published, fillable and in the manifest. Only the editor's catalogue view
changes. The edit lock IS honoured, also matching `/label` -- hiding a kit out
from under someone mid-edit is the disruption that lock exists to stop.

**It fails visible.** `_is_hidden` returns true only for a literal `True`;
absent, null, `"false"`, a hand-edited string, unreadable metadata all mean
visible. A kit must never vanish from the only list that shows it because a
parse went wrong -- hiding has to be something a human chose.

## One filter, four render sites

Each catalogue renders its kits twice (card grid and `<select>` strip), and
there are two catalogues (hosted and local folder). That is four renders of one
list. Filtering at each site is four chances to disagree, and **a strip offering
a kit the cards deny is worse than no filter at all**, so the decision lives in
one module (`catalogueFilter.ts`) that both entry types satisfy structurally
without either importing the other.

Search covers the **label and the id**. The id matters because every server
refusal names a kit by id (bd `kztlr`), so an operator reading an error pastes
that in -- searching only labels would fail exactly the person who most needs to
find the kit.

The bar stays out of the way until there is enough to scan -- above three kits,
or whenever anything is being withheld or the filter is active. (That second
half was not in the first draft, and review found it mattered; see below.) A
"N not shown" line renders whenever the filter is holding anything back, because
a filtered-out kit that looks identical to a deleted one is what makes people
distrust a filter.

## Both write paths, or local silently ignores it

Local mode reads `metadata.json` directly rather than through the backend, so a
flag wired only on the hosted path would be invisible there -- and "hidden"
would mean different things on the two surfaces of one store. The local reader
reads the same key, and the local Hide button routes through the same backend
endpoint local mode already uses for status changes. One implementation cannot
drift from itself.

Local mode has **no role concept** -- it is the maintainer's own machine and
their own folder -- so there is no editor/author split to enforce there. The
server still checks; the button is not the guard.

## What the repo's own guards caught

Two set-pinning tests failed on the new route, both correctly:

- `test_every_ekr_route_is_accounted_for_by_the_write_lock_partition` refused to
  let a new route ship unclassified, and demanded a written reason. It is
  recorded as write-lock exempt, with the argument above.
- `test_every_shipped_route_is_in_the_guide_routes_table` required a
  `technical_guide.md` row, and a second check required it in sort order.

Neither is a nuisance. They are the enumerate-the-set discipline working on
somebody who did not know the sets existed.

## A mutation-testing note worth keeping

The fail-safe test survived its own mutation at first, and the parametrize list
looked thorough. Every row was falsy or `True` -- so truthiness and identity
agree on all of them, and `bool(...)` passed. **Truthy-but-not-`True` is the
half that matters** (`"false"`, `"no"`, `1`, `[0]`); the string `"false"` is the
sharpest, since a human hand-editing metadata writes it MEANING not-hidden.

Worse: for two of those runs my `-k` filter did not match the test's name, so
the "survived" verdict was measuring nothing at all. Read the collected count,
not just the verdict.

## Review: my own threshold could strand a kit

I flagged the `> 3` filter-bar threshold as my own risk and asked review to check
it. It was right to: gated on the raw kit count alone, a hidden kit in a
two-kit store vanished from both surfaces **and the "Show hidden" control that
would bring it back never rendered**. The bar that is the only way out was
hidden by the same rule that hid the kit. That is exit criterion 2 failing
outright, not a rough edge.

The gate now also renders whenever anything is being withheld or the filter is
doing something. **The way back must never be conditional on how many kits you
happen to have.**

Two more, both real:

**The open kit.** Hiding the kit currently being edited left the editor pane
showing it while its card left the catalogue, and the strip's controlled
`<select>` pointing at an id its own option list no longer offered. Delete
already unwinds exactly this (bd `hbfky`, with a comment saying why); hiding
needed the same. Only on hide -- unhiding an open kit is fine, it is returning
to a list the editor never left it for.

**The per-status counts.** `2 in progress` sat above a one-card grid, because
the summary summed the raw list while describing the filtered one. It now
counts what is shown.

Worth separating from that: the `N forms in the shared workspace` banner
deliberately counts the STORE and says so in its own words. That is a different
claim, not a contradiction -- and it is how an operator learns the store holds
more than they are looking at. My first test asserted it should change, which
would have removed the one line telling them so. Only the summary that
*describes the grid* had to follow the grid.

## A mutation that survived, again

Two of the three fixes reddened their tests immediately. The summary fix did
not -- nothing asserted the per-status counts at all, so changing them back was
invisible. The line was fixed and unpinned, which is the same thing as unfixed
one refactor later.

That is twice in this bead that a green suite meant "nothing tests this" rather
than "this works" (the other was the fail-safe parametrization). Both times the
tell was identical: I reverted the fix expecting red and got green.

## Round 2: I fixed one catalogue and not its twin

Three more, and the first is the plainest kind of miss. The open-kit unwind
landed in the hosted catalogue and **not in the local one** -- same button, same
bug, one of two places. Fixing the instance and not the set, in a bead whose
whole shape is "there are two catalogues and four render sites".

**The strip could act on a kit it was not offering.** The dropdown renders the
filtered list; the action row beside it resolved its target from the raw one. So
with the selected kit hidden, the `<select>`'s value matched no rendered option
-- the browser shows something else -- while those buttons still operated on the
hidden kit. A row naming form A and acting on form B. Both lookups now resolve
against what the dropdown offers.

**A concurrent hide.** Another author hides the kit I have open; I learn of it
on my next refresh, and nothing in my session called the handler that unwinds
it. An effect now closes the editor when the open kit arrives hidden -- keyed on
*hidden*, not on absent-from-view, because my own search box narrowing the list
must never close the form I am editing. That distinction has its own test.

## Two vacuous tests, one after the other

The action-lookup and local-unwind fixes both survived their mutations at first.

The local one is the instructive failure. My test clicked "Open form-kits
folder" and then asserted `clearOpenKit` had been called -- but **opening a
folder calls `clearOpenKit` itself**, so the assertion was already satisfied
before the Hide click happened. It passed identically with the fix removed.
Clearing the mock immediately before the click fixed it.

That is three times in this bead that reverting a fix produced green. Each time
the tell was the same, and each time I only saw it because I ran the mutation
rather than trusting the new test's name.

## Round 3: my fix for the desync made hidden kits unopenable

I asked review to check whether the concurrent-hide unwind had broken opening a
hidden kit deliberately. It had.

The effect keyed on the STATE -- "the open kit is hidden" -- which is equally
true when someone ticks Show hidden and clicks a hidden card on purpose. So the
editor opened and immediately closed itself. A fix for one desync creating a
dead end: exit criterion 2 failing again, in a new way, from the repair of the
last failure.

It now fires on the **transition**: visible last render, hidden now. Arriving
hidden is a deliberate act and is left alone.

**The first attempt at that was still wrong**, and the reason is worth keeping.
A boolean "was it visible?" flag starts false, but `kits` starts EMPTY -- so on
the first render the open kit is absent, which read as "not hidden", set the
baseline, and then flipped when the list loaded. Indistinguishable from a real
transition. The flag is now tri-state: **unknown** until the open kit is
actually present in a loaded list, so an absent kit teaches the baseline
nothing. Both directions are pinned -- over-firing reddens the deliberate-open
test, under-firing reddens the concurrency one.

**And the concurrency test that was meant to catch this could not.** It mounted
with the kit already hidden, which is the deliberate-open case, so it passed
against both the right behaviour and the wrong one. It now drives the real
sequence: render visible, assert nothing closed, then refresh with it hidden.

That is the fourth vacuous test in this bead, and they share a shape: **the
setup asserts the end state rather than performing the change**. Mounting
already-hidden is not the same event as becoming hidden, any more than a folder
open that itself calls `clearOpenKit` is the same as a Hide click doing so.

## Round 4: effect ORDER was doing load-bearing work

Two more. The first is the same unopenable-hidden-kit bug a third time, reached
a third way.

I had split the logic across two effects: the unwind, then a reset keyed on
`selectedKitId`. Effects run in declaration order, so switching straight from a
visible kit to an already-hidden one ran the unwind FIRST, against the previous
kit's stale "visible", and closed the kit just opened. The reset that would have
cleared it ran a line too late.

The fix is not to reorder them. It is to stop depending on order at all: the
baseline is now stored **with the id it describes**, in one effect, so "was THIS
kit visible?" is answerable without a second effect having run yet.

**And no existing test could have caught it**, which is the more useful half.
Every test here mounts fresh, and this bug needs a *prop change on a live
mount* -- which is how the real path works: the catalogue is already up, you
tick Show hidden, you click a card, `App` sets `selectedKitId`. A `rerender`
test now covers it, and reverting the id-pairing reddens exactly that test.

**The local catalogue had no concurrent unwind at all.** I had reasoned that
local mode is single-user -- but that is true of the FOLDER, not the endpoint:
local writes hiding through the same shared backend, so another session can hide
the kit open here. Same fix, same shape, now in both.

## What five rounds actually cost, and why

Nothing shipped wrong. But the same defect -- an open hidden kit closing itself
-- appeared three times, through three different mechanisms: state instead of
transition, then an empty-list first render, then effect ordering. Each fix was
correct for the case in front of me and left the next one open.

The tell I kept missing: I was reasoning about *when the effect fires* rather
than *what it needs to know*. Once the answer became "was this specific kit
visible a moment ago", the id-paired baseline made all three cases fall out at
once, and there was no ordering question left to get wrong.

The other recurring cost was test shape. Four vacuous tests, and one absent one,
all sharing a cause: **mounting in the end state instead of performing the
change**. A fresh mount cannot see a transition, and an assertion satisfied by
the setup proves nothing about the code under it.

## The cross-surface pass: one real gap, and it was mine

The outer review traced the contracts outward and confirmed the thing I most
wanted checked: **no metadata writer reconstructs from a fixed field list.** All
ten backend `put_metadata` sites and all three local writers merge with a
spread, so hide-then-rename/publish/retire cannot silently unhide a kit. The
deploy scripts' `metadata.json` greps look for quoted strings, and `hidden` is a
boolean, so it cannot be captured by them. A hidden-but-published kit stays
fillable, in the manifest, and reachable by a client -- hiding is an
editor-view concept and stays one.

The gap was elsewhere, and it is a genuine data-loss path I introduced:

**Hiding the open kit silently discarded unsaved edits.** `clearOpenKit` wipes
the schema and the whole undo stack. Its two existing callers were both already
guarded -- the folder switch asks, and the delete unwind follows a destructive
confirmation dialog. Hiding made it **one click, with no prompt**, and its own
tooltip promises "nothing is deleted and you can bring it back at any time" --
true of the FORM, and not of the edits in front of you. The concurrent case was
worse: another author's hide would destroy my unsaved work on my next refresh.

Now gated by `confirmDiscardOnHide`, threaded from App to both catalogues, and
consulted **only** when the kit being hidden is the open one and there is
actually something to lose -- so the common case stays a single click. Unhiding
never closes anything and is never gated. Both directions are pinned: removing
the guard reddens one test, asking on every hide reddens the other.

**Five inner rounds could not have found it.** Every catalogue test stubs
`clearOpenKit` with a mock, so what happens *behind* that callback is invisible
there -- the loss lives one component up, in App. That is precisely the
cross-surface reviewer's job, and the split earned its keep here: the inner loop
verified the contract was called correctly, and the outer one asked what
answering that call actually costs.

## Round 6, and a leak the full suite caught

The re-clear returned NO-GAPS. The reviewer filed two beads rather than
blocking, and one was worth doing immediately: the new guard was tested in the
hosted catalogue only. Given that this bead's own history is three rounds of
fixing one catalogue and missing its twin, shipping the guard with coverage on
one of two call sites repeats that at the test layer -- a refactor dropping the
clause from the local file alone would pass the whole suite. It now reddens.

**Then the full suite caught something isolated runs could not.** My new test
replaces `global.fetch`, and its `describe` block had no `afterEach` to restore
it -- so the stub leaked into every later file. Ten unrelated tests failed in
the full run while this file passed alone. The sibling block above it already
restored; mine did not, and that was the entire difference.

Worth naming because it is the third distinct way this bead produced a green
signal that meant nothing: a vacuous assertion, an absent transition test, and
now a file that passes alone and breaks its neighbours. **Only the full-scope
run can see the third kind** -- which is why it is the gate rather than a
formality.
