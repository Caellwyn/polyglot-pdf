---
date: 2026-07-09
bead: polyglot-pdf-15ic
title: "Rename a form's display label after onboarding"
tags: [schema-editor, form-kits, ui]
---

## Trigger

Maintainer (2026-07-09): "we also need a way to change the name of forms after
they are added, so we don't end up with form, form 2, etc." Onboarding derives
the display label from the PDF filename, so nameless uploads collide into
"Form", "Form 2", ... and nothing could fix them afterwards.

## Design (from the identity-model exploration)

Three name-like strings exist; only the DISPLAY label needed renaming:
- `kit_id` (directory / GCS prefix): the immutable identity everything keys on
  (manifest, fill route, voice handshake, storage paths). Deliberately NOT
  renameable -- a rename would be a storage move with breakage risk.
- `metadata.json label`: the catalogue + voice-picker display name. Pure
  display; nothing keys on it. THIS is what renames.
- `form_metadata.title` (in schema.json): an editor subtitle only; untouched.

## What shipped

- **Backend**: `POST /api/editor/kits/{kit_id}/label` (editor tier), the exact
  read-merge-write shape of the status flip -- `{**meta, "label": stripped}`
  via `store.put_metadata` (works for both Local and GCS stores through the
  FormKitStore abstraction). Blank label -> 422; unknown kit -> 404; the label
  VALUE is not logged (value-free server logs).
- **Hosted client + strip UI**: `setRemoteLabel` beside `setRemoteStatus`; a
  Rename button in the selector strip for the SELECTED kit -- deliberately NOT
  gated on the parent-confirmed open (rename is metadata-only; no open
  involved, unlike Mark-complete), swapping to an inline input (prefilled with
  the current label; Enter saves, Escape cancels) + Save/Cancel. Success
  refreshes the catalogue and shows a notice.
- **Local mode**: `setKitLabel` mirroring `setKitStatus` (read-merge-write of
  metadata.json) + the same inline Rename control on each FormCatalogue card.

## Verification

- Backend: 4 new route tests (rename preserves other metadata keys + strips
  whitespace; blank -> 422 unchanged; unknown kit -> 404; no token -> 401).
- Stores: setRemoteLabel unit test (POST shape + refusal detail);
  setKitLabel tests (trim + preserve + blank-rejects-without-write).
- Strip: rename-flow test (prefill, save -> setRemoteLabel with the trimmed
  label -> refresh) + Escape-cancels-without-a-server-call.
- LIVE end-to-end (hosted preview + local backend on a THROWAWAY kits copy):
  renamed "W7 2" -> "W-7 Renewal (copy 2)" through the strip UI (prefill,
  notice, dropdown refreshed); a route-level rename of the complete i-90
  propagated to the voice-app manifest with kit_id/paths untouched -- in
  LOCAL-store mode, whose manifest derives labels live from metadata.json.

## The GCS/deployed manifest gap (fresh-eyes catch, fixed here)

In the DEPLOYED (GCS) mode the voice manifest is a STATIC index.json that only
the deploy scripts regenerate -- and both derived `label` from the schema's
`title`, never metadata.json's `label`. So a rename would have shown in the
editor but NEVER reached the deployed voice app (exit criterion 2 failing on
the real deployment target). Fixed: `deploy-all.sh` + `scripts/deploy-form-kit.sh`
now use the store's own precedence (metadata `label` -> schema `title` ->
kit_id), so a rename reaches the deployed voice picker at the next form-kits
deploy -- the same pipeline every other kit change (status, schema edits)
already rides. Verified: the extraction pipeline pulls the label from a real
metadata.json and falls back cleanly when it is absent; only the COMPLETE i-90
is in the deployed manifest today, and its metadata label ("I-90 (Green Card
Replacement)") is the cleaner name the editor already shows.

Also added a 200-char label cap (422) against accidental huge pastes.

## Manifest-poison guard (Opus review catch, fixed here)

The deploy scripts extract the label with a grep/sed pipeline and splice it
into index.json by STRING CONCATENATION -- so a route-legal label containing a
double quote or backslash would truncate the extraction and ship INVALID
manifest JSON (the voice app then fails to parse it: no forms load; the
scripts' json.tool check even falls back to uploading the raw broken JSON --
filed as bd 4w0l for a fail-hard). Fixed at the single choke point: a shared
`_safe_label` validator (blank / >200 chars / double quote / backslash /
control chars -> 422) used by BOTH the rename route AND the onboard route's
optional caller-supplied label (the second entry point for the same poison).
Test pins all three poison shapes rejected with metadata unchanged.

## Notes

- Onboarding already accepts an optional label the upload UI never sends --
  prompting for a name AT upload would prevent the collision up front; left as
  a follow-up (the rename now makes it recoverable either way).
