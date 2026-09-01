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

The bar appears only above three kits: a filter over three rows is noise, and
the demo store crossing that threshold is why the bead exists. A "N not shown"
line renders whenever the filter is holding anything back, because a
filtered-out kit that looks identical to a deleted one is what makes people
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
