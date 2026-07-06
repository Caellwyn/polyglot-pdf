---
date: 2026-07-06
bead: polyglot-pdf-d0k
title: "Remove the tokenless standalone connection path in VoiceOverlay / VoiceOverlayMobile"
tags: [security, refactor]
---

## Trigger

Maintainer decision (2026-07-06): ALL connections must carry an auth token.
Google shut the app down for a tokenless connection, and it is bad security on
an app this expensive to run; the legacy bookmarklet is NOT being resurrected.
The standalone branch in these two overlays created its OWN ConnectionManager
via `createConnectionManager(...)` WITHOUT a getToken callback when no
`connectionManager` prop was passed -- exactly the tokenless path to eliminate
(bd polyglot-pdf-d0k, a fresh-eyes finding on PR #94).

## What shipped

- **frontend/src/demo/VoiceOverlay.tsx** + **VoiceOverlayMobile.tsx**: removed
  the standalone `createConnectionManager(...)` branch from the connection-init
  useEffect. The overlays now ONLY adopt the `connectionManager` passed by the
  parent (which always registers the token). Removed the dead
  `SchemaFormStateManager.init(schema)` that fed only that branch, the
  self-created-manager disconnect/cleanup, and the now-unused
  `createConnectionManager` import. `connectionManager` is now a REQUIRED prop
  on both (was optional) -- so a tokenless connection is structurally impossible
  here.
- **frontend/src/demo/VoiceOverlayResizeFlip.test.tsx**: the only two tests that
  omitted `connectionManager` to exercise the (now-removed) standalone path were
  updated to pass a disconnected mock manager; removed the now-dead
  `vi.mock('../shared/connection')` stub of `createConnectionManager` (neither
  component imports it anymore); renamed the two "fresh/standalone mount" titles
  to "fresh/disconnected mount".

## Why this is a clean removal (not a behavior change)

Production was already tokenful: `SchemaForm.tsx` (the sole non-test render
site) gates on `connectionManager && streamReady` and ALWAYS passes the
token-registered shared manager. The standalone branch was dead on the
production path. The other overlay tests (disclaimer, reconnectbutton,
listeningIndicator) already mock `createConnectionManager` to a no-op AND inject
a mock `connectionManager` prop -- they never exercised the standalone creation
and pass unchanged. Grep confirmed no bookmarklet / other standalone entry
exists.

## Verification

Overlay test suite (4 files) 29 tests pass; `tsc --noEmit` clean; full frontend
suite 751 passed (37 files, non-shrunken). Exit criteria confirmed
independently: `grep createConnectionManager` in the two overlays returns
NOTHING (criterion 1), and `connectionManager: ConnectionManager` is a required
prop on both (no `?`).

## Doc freshness

None -- the overlays are demo/UI components; no tier-1/2 doc tracks the standalone
path (it was legacy bookmarklet plumbing).

## Note

The `bd update` that added the retrospective exit criteria initially mangled the
bead description (an inline `bd show --json | python` returned a list, not a
dict, so the substitution emptied the description). Caught immediately and
restored the full original investigation text + resolution + criteria before
dispatching -- the bead history is intact.
