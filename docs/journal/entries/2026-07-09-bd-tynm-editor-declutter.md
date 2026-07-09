---
date: 2026-07-09
bead: polyglot-pdf-tynm
title: "Editor UI declutter: catalogue collapses to a dropdown; slim validation strip"
tags: [schema-editor, ui]
---

## Trigger

Maintainer (2026-07-09, with screenshot): the editor view is too cluttered --
"the bottom progress bar takes up too much space, and the top thing is not
always necessary to see all forms. They can be a drop down. A lot of what's in
this view needs to be reduced in footprint."

## What shipped

All footprint comes out of fixed-height siblings of the flex-1 work area, so
every saved pixel goes straight to the PDF/fields/properties columns:

1. **Form catalogue -> compact selector strip** (`RemoteCatalogue.tsx`, the
   hosted surface the maintainer/contractor use). The always-expanded card grid
   is now COLLAPSED by default behind a one-line strip: a `<select>` listing
   every kit (label -- status, review %; schemaless kits marked "no schema
   yet"), the selected kit's status badge + its actions (Mark complete / Revert
   to draft / Run extraction), and a "Show form cards" toggle that restores the
   full grid. Selecting a schema-bearing kit opens it; a schemaless kit is
   selectable for its actions without opening. A `defaultExpanded` prop
   preserves the card-first rendering for tests/embedders.
2. **Validation & Progress -> slim strip** (`ValidationPanel.tsx`, both modes).
   The fixed h-48 (192px) region with three text-2xl stat cards is now ONE
   auto-height line: thin progress bar + "N% -- x complete, y need review, z
   total" + error/warning counts + Repair-all; findings expand below in a
   capped scroller. Measured live: 33px vs the old 192px.
3. **Header + catalogue padding** p-4 -> px-4 py-2 (`App.tsx`,
   `RemoteCatalogue.tsx`).

## Verification

- Live hosted preview (vite --mode hosted + a local backend with probe tokens,
  driven via the preview tools): the gate passes, the strip renders all 5 kits
  with statuses/percentages, NO card grid by default, "Show form cards"
  present; selecting I-90 from the dropdown opens it against the real backend
  and the slim bottom strip shows its live stats (86%, 114/132) at 33px. No
  console errors. (Pixel metrics beyond the bottom bar are unreliable in the
  0x0 sandbox viewport; the structural snapshot is the record.)
- Tests: new strip suite (collapsed default; dropdown opens schema-bearing /
  only-selects schemaless; toggle round-trip); existing card tests render with
  `defaultExpanded`; the Mark-complete unsaved-edits guard asserted on BOTH the
  strip and card copies; App.hosted flows rewritten to open kits through the
  dropdown (the real user flow now). Full editor suite 36 files green; tsc
  clean.

## Deliberate scope calls

- The LOCAL FormCatalogue keeps its card grid (the exit criteria name the
  hosted editor; local is the dev-only File-System-Access flow). Mirroring the
  strip there is a cheap follow-up if wanted.
- The instructions-PDF attach for extraction stays on the CARDS (one toggle
  click away); the strip carries the common bare Run extraction (which works
  without instructions since bd 1ysc).
- Known edge: re-selecting the kit the dropdown already shows cannot re-fire an
  open (native select change semantics); the cards cover that rare retry.

## Fresh-eyes fixes (folded in)

- **Unconfirmed-open desync (the real gap).** The strip's selection is
  optimistic (set on change, before the async open resolves), so a FAILED open
  would have left the strip offering Mark-complete/Revert for a kit that never
  loaded. Fixed: status-changing actions render ONLY for a kit whose open the
  parent confirmed (`kit.id === selectedKitId`), or for schemaless kits (no
  open semantics -- Run extraction stays reachable). The optimistic selection
  resets whenever the parent confirms an open by any route. Regression test
  pins the unconfirmed case; live preview re-verified both states.
- HostedGuide's three "on the form's card" mentions now name the selector
  strip / the Show form cards toggle.
