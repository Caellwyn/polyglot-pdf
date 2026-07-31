---
date: 2026-07-31
bead: polyglot-pdf-wjxs
title: "The overlay matched widget names literally, so i-90 read as 78% unclaimed"
tags: [authoring, form-kits, review-tooling]
---

## Trigger

Found while reviewing bd `polyglot-pdf-a1xt`: `overlay_field_guesses.py` reported
**152 of i-90's 195 widgets as "unclaimed"** (blue), while w7 and f1040 resolved
almost perfectly. That blue is supposed to mean a coverage gap -- a widget no
field claims -- so on the kit with the highest assignment risk the tool's headline
signal was mostly noise.

## Root cause

The overlay keyed its claims map on the schema's `pdf_field_name` string and
looked widgets up by exact equality. i-90's schema stores the **XFA leaf name**
(`P1_Line10_CityTownOfBirth[0]`) while the PDF's widgets carry the
**fully-qualified path** (`form1[0].#pageSet[0].Page1[0]...P1_Line10_CityTownOfBirth[0]`).
Exact matching therefore missed **146 of 189 claims**.

Every other consumer in the repo already resolves this correctly, with the same
convention: exact match first, else a **dot-boundary** suffix match.

- `backend/services/schema_lint.py::_match_dump_names`
- `backend/routes/pdf_fill_routes.py::find_widget`
- `backend/services/schema_repair.py::_check_widgets_exist`

The overlay was the only one matching raw strings. The dot boundary is
load-bearing -- a bare `endswith` would let `x_name[0]` claim `prefix_x_name[0]`.

## The second defect, which the first was hiding

Because two claims written differently never met, a genuine multiclaim spanning
the two naming styles was **invisible**: each claimant sat under its own
unresolved key, so the widget looked singly-claimed from both sides. Resolution
had to happen for the multiclaim signal to work at all on such a kit.

## What shipped

`_resolve_claimants(claimants, widget_names)` re-keys the map from schema names
onto the PDF's actual widget names, mirroring `_match_dump_names`.

The subtle part is **ordering**, and I got it wrong first. `_claims` applied
lint's multiclaim rule (including the benign *groups-of-one* carve-out: a field
plus a single option of the same field) and returned collapsed labels. Resolving
*after* that re-created the pair: i-90's `P7_checkbox7Extend[0]` writes its
field-level claim as the full path and its option claim as the bare leaf, so they
collapsed separately, then merged post-resolution into a **false multiclaim** on
a correct binding.

So the pipeline is now explicit and ordered:

```
_claimants(schema, mode)          # (owner, kind) -> label, NOT yet collapsed
  -> _resolve_claimants(..., widget_names)   # re-key onto real widget names
  -> _collapse_claimants(...)               # THEN apply lint's multiclaim rule
```

`_claims()` is kept as the collapsed convenience wrapper for callers with no PDF
to resolve against.

## Measured

| kit | before | after |
|---|---|---|
| i-90 | 43 labelled / 152 unclaimed | **188 labelled / 7 unclaimed** |
| f1040 | 187 / 12 | 187 / 12 (unchanged) |
| w7 | 67 / 2 | 67 / 2 (unchanged) |

`multiclaimed` is 0 on all three -- the false positive my first ordering
introduced is gone, and w7's 2 unclaimed are still the two `ivh9` write-ins that
kit deliberately leaves unmodelled.

## Verification

- 6 new tests: leaf->qualified resolution, the dot-boundary requirement,
  exact-beats-suffix, resolution-before-collapse (the ordering bug, pinned with
  i-90's real shape), a genuine cross-style multiclaim still surviving, and w7
  unchanged as the no-op guard.
- Full backend suite: 2378 passed, 2 skipped.
- **No form kit was modified.** `form-kits/` is read-only by maintainer
  constraint -- i-90 in particular is the verified golden copy used for demos --
  so the w7 test writes its output to `tmp_path`. (A first draft of that test
  wrote into the kit directory; caught and fixed before commit.)

## Note

The editor-side overlay (bd `polyglot-pdf-w70y`) is immune to this entire class:
it keys on `field.pdf_position` rects rather than widget names, so it never has
to resolve a name at all.
