---
date: 2026-07-06
bead: polyglot-pdf-nivy
title: "P5.3c author-tier 'Add from PDF widgets' option picker"
tags: [schema-editor, conventions]
---

## Trigger

The last of the three sub-beads P5.3 (`h76m.14`) was split into (after P5.3a
`v96b` store-with-issues and P5.3b `zgln` repair-all). Depends on P5.3a for the
persisted AcroForm dump artifact.

When the extractor consolidates a checkbox/radio group it sometimes MISSES a box:
the widget exists in the PDF but no field/option in the schema claims it. Before
this bead the author had to hand-type the missed option's `pdf_field_name`. This
adds a picker over the form's unclaimed PDF button widgets.

## What shipped

- `backend/services/widget_picker.py`: `unclaimed_button_widgets(schema, dump)`
  -- the dump's checkbox/radio widgets that NO field/option `pdf_field_name`
  claims. Claiming reuses `schema_lint`'s `_dump_names` + `_match_dump_names`
  (exact, else dot-boundary suffix), so the picker and the widget-claim lint rule
  agree on what a `pdf_field_name` resolves to. Pure function; empty without a
  dump (the pre-v96b kits). Each result carries `name` / `type` / `on_value` /
  `tooltip` / `page` -- everything the picker needs to mint an option.
- `GET /api/editor/kits/{kit_id}/unclaimed-widgets` (author tier -- it feeds an
  edit that adds a PDF-mapped option): loads the kit schema + persisted
  `acroform.json`, returns the unclaimed widgets. 404 for an unknown/schemaless
  kit; 403 for the editor tier.
- `remoteKitStore.loadUnclaimedWidgets(kitId)`.
- `FieldEditor`: a `WidgetPicker` SUB-COMPONENT (its own hooks, so it can render
  inside the options section without tangling FieldEditor's early
  `if (!field)` return -- a hook at the top level of FieldEditor after that
  conditional return would break rules-of-hooks). Shown for
  `checkbox_group`/`radio` fields in hosted author mode (the callback is passed
  only then). Selecting a widget appends an option whose:
  - `label` = the widget's `/TU` tooltip, else its leaf name;
  - `value` = a slug minted from that label via `mintUniqueSlugs`, UNIQUE against
    the field's existing option labels (so adding a widget can't manufacture a
    duplicate option value);
  - `pdf_field_name` = the widget name; `pdf_on_value` = its on-state.

## Why the picker is a sub-component

FieldEditor early-returns the metadata panel `if (!field)`, so no hooks may run
at its top level after that point. The picker needs state (widget list, open,
loading, error). A self-contained `WidgetPicker` with its own hooks, rendered
only where `field` is non-null, keeps rules-of-hooks intact and keeps the network
fetch (via the injected `onLoad` callback) out of the pure render path -- App
owns the actual `loadUnclaimedWidgets` call, matching the editor's separation
(App = I/O, components = render + callback).

## Verification

Exit criterion ("an author can add a missed checkbox to a group and the result
is lint-clean"): verified end-to-end -- after the picker appends the option, the
schema lints 0 errors / 0 warnings (both boxes now claimed, so the
`dump-widget-multiclaim` rule does not fire and the minted slug passes the
slug rule) and `unclaimed_button_widgets` then returns [] (nothing left to add).
Backend: 6 `widget_picker` service tests + 4 route tests (unclaimed list,
empty-without-dump, author-gate 403, unknown-kit 404), 91 editor tests total,
592 backend tests green. FE: 5 FieldEditor picker tests (correct mapping, unique
slug on label collision, empty-state note, gating without the callback, inline
error); touched suites green; typecheck clean. Full FE suite via CI's Linux
runner (the local vitest fork-pool hangs -- see the v96b entry).

## Unblocks

P5.3 is now complete across all three sub-beads (`v96b` + `zgln` + `nivy`). P6.1
(migration) depends on all three.
