---
date: 2026-07-13
bead: polyglot-pdf-jzvs
title: "Static form-kit fallback errored in backend-less local dev: the MODAL fetched /api/form-kits with no fallback, not the parent"
tags: [schema-forms, frontend, local-dev]
---

## Trigger

With no local backend on :8000, `SchemaFormDemo` showed "Unable to load
available forms" even though the static fallback fetch `/form-kits/index.json`
returned 200 with a valid manifest (verified by fetching + parsing it in the
same page). A local-dev-only annoyance -- production always has the backend --
but it defeated the documented backend-less static path.

## Root cause

The visible error did not come from `SchemaFormDemo`'s manifest loader. That
loader has the intended backend -> static fallback: it tries
`GET {backend}/api/form-kits`, and on any failure fetches
`/form-kits/index.json` and populates `forms` -- which worked (that is why
index.json returns 200 and the list resolves at the parent level).

The error came from `LanguageSelectionModal`, which did its OWN independent
`GET /api/form-kits` fetch with **no static fallback**. In backend-less local
dev that fetch rejects (connection refused), the modal's catch runs
`setError('Unable to load available forms')`, and its error wizard step
renders. So the parent had the forms in hand while the child modal, rendered on
top, showed a fetch error for a list it never needed to fetch -- the parent
already owned it.

The bead's own hypotheses (an error propagating out of the parent's catch, or a
race with the `devConsoleCapture` POSTs to the dead backend) were not the cause:
`devConsoleCapture` swallows its own transport errors and never throws
synchronously, and the parent's catch populates `forms` correctly. The
duplicated, fallback-less fetch in the modal fully explains the symptom.

## Fix

Made `LanguageSelectionModal` purely presentational. `SchemaFormDemo` already
resolves `forms` (with its fallback) and only renders the modal past its
`manifestLoading` / `manifestError` / `!forms.length` early returns, so the
list is guaranteed populated by mount time. The parent now passes `forms` down
as a prop and the modal no longer fetches, no longer has loading/error wizard
steps, and no longer imports `getBackendHttpUrl`.

The `forms` prop is optional (defaults to `[]`) because the two VoiceOverlay
callers (`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`) always pass
`preselectedFormId`, which seeds `selectedFormId` non-empty so
`handleLanguageSelect` completes via `onSelection` immediately -- the
form-selection step (the only consumer of the list) is unreachable there, and
was in the old fetch path too. Also removed two pre-existing dead locals
(`canSubmit`, `showFormSelector`).

Added a jsdom regression test
(`LanguageSelectionModal.test.tsx`): renders the modal with a `global.fetch`
mocked to reject, asserts the language step renders, the old
"Unable to load available forms" string never appears, and `fetch` is never
called; plus the props-driven form-selection path and the preselected-form
(VoiceOverlay) path.

## Verification

- New test: 3/3 pass. Broader `schema-forms` + `demo` vitest suites: 568-598
  pass (default forks pool), no regressions.
- `tsc --noEmit`: clean (proves the optional-prop wiring across all three
  consumers).
- Full backend suite in closeout prep: 1011 passed. Browser drive of the live
  page was blocked by the Firebase auth gate (account creation / password entry
  is barred), so verification rests on the deterministic jsdom test that
  reproduces the exact dead-backend failure condition.

## Docs

closeout doc-freshness flagged many tier-2/3 docs STALE, but every flag traces
to backend `2026-07-12` edits (config.py, callback_handler.py, connection.ts,
schemaFormState.ts, etc.) that this branch did not touch -- pre-existing
staleness unrelated to jzvs. No doc references the modal's old fetch behavior,
so none needed updating for this change.
