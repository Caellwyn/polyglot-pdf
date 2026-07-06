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

## Review fixes (pre-PR)

Four real bugs caught before the PR. (0b, Opus fallback) Even after surfacing
every shared-name kid, the picker built the WRONG v2 shape for them: it set
`option.pdf_field_name = <shared name>` on EVERY option, so two options of one
radio field claimed the same widget name -> `dump-widget-multiclaim` ERROR (the
result was NOT lint-clean). The correct shared-name shape puts the name on the
FIELD and only `pdf_on_value` on each option. Fixed: the backend candidate now
carries a `shared_name` flag (true when a dump entry has >1 kid); the picker
branches -- a shared-name kid sets `option.pdf_on_value` and lifts the widget
name onto the FIELD's `pdf_field_name`; a distinct-name widget keeps
`option.pdf_field_name`. Verified: the picker-built shared-name group lints 0/0.
(0, fresh-eyes) `unclaimed_button_widgets`
read only `widgets[0]` of a dump entry, so a TRUE single-name AcroForm radio
group (one field name, N kids differing only by `on_value` -- a documented v2
shape on USCIS/legal forms) surfaced only its FIRST kid, and once any option
claimed that shared name, the rest became permanently unreachable -- the exit
criterion failed for that whole class of forms. Fixed: the picker now emits one
candidate PER kid widget, and claiming is per `(name, on_value)` -- a whole-name
claim (per-widget group / standalone) shadows every kid; a kid claim
(`(name, on_value)`) shadows only that kid, so a partly-mapped shared-name group
still offers its unmapped kids. Verified end-to-end (adding the Female kid ->
lint 0/0) with four new service tests. Then: (1) fresh-eyes -- the WidgetPicker minted the
new option slug unique against existing option LABELS, but `option-value-duplicate`
keys on VALUE, so a hand-edited value colliding with the new label's slug would
slip through as a duplicate-value ERROR (breaking the lint-clean criterion);
fixed to dedup against existing option VALUES. (2) typecheck -- `FieldOption`
(frontend type) lacked `pdf_on_value`, which the picker sets from the dump's
`on_value`; added it (the backend model already has it) so a picked box
round-trips fillable. Both verified: the collision case mints `family_2` and the
result lints 0/0.

## Opus fallback re-review (folded in)

The re-review confirmed the shared-name fix `NO-GAPS` and found two non-blocking
in-scope quality issues, both fixed here: (a) the picker list keyed rows on
`w.name`, but a shared-name group returns N candidates with the SAME name ->
duplicate React keys; now keyed on `name|on_value`. (b) the `onPick` field-name
lift was gated only on presence, so a rare shared-name CHECKBOX matrix
(widget_count>1) could lift a `pdf_field_name` onto a checkbox_group (v2 forbids
it -> un-promotable). Fixed at the source: `shared_name` is now RADIO-ONLY in the
backend (a multi-widget checkbox entry stays distinct -> per-option
`pdf_field_name` -> fillable), plus a belt-and-suspenders `field.type === 'radio'`
guard on the call site. This also means the picker no longer emits the
unfillable pdf_on_value-only checkbox shape that bd `polyglot-pdf-u632` tracks at
the filler (u632 stays open for hardening the filler against a pre-existing such
schema; this diff just stops the picker being a source of it).

## Doc-freshness note

closeout_prep flagged the usual tier-2 docs as STALE. Reviewed: `schema-forms.md`
tracks `frontend/src/schema-forms/types/schema.ts` (the VOICE app), not the
`schema-editor/src/types/schema.ts` this diff edited (a different app) -- and no
other doc tracks a file this diff touched. Pre-existing drift, left as-is.

## Unblocks

P5.3 is now complete across all three sub-beads (`v96b` + `zgln` + `nivy`). P6.1
(migration) depends on all three.
