---
date: 2026-08-28
bead: polyglot-pdf-uibly
title: "fix(schema-editor): handleRename/handleUploadPdf leave busy=true on an auth-error return"
tags: [schema-editor, frontend]
---

## Trigger

`RemoteCatalogue.tsx`'s `handleRename` and `handleUploadPdf` set
`setBusy(true)` before their `await`, then on a caught `AuthError`/
`ForbiddenError` called `onAuthError?.(err)` and returned WITHOUT resetting
`setBusy(false)` -- unlike the non-auth-error branch a few lines below,
which does reset it, and unlike every OTHER handler in this file
(`handleDelete`, `handleLock`, `handleSetStatus`, `handleTranslateOptions`,
`handleRunExtraction`), which reset busy in a `finally` block that runs on
every exit path.

Currently harmless in the shipped app: `onAuthError` routes to
`handleAuthExpired`, which sets `role=null`, causing `App.tsx`'s early
`if (hosted && !role) return <SignInGate />` to unmount `RemoteCatalogue`
entirely -- so the orphaned `busy=true` is discarded with the component. But
it's a latent trap: if `RemoteCatalogue` is ever kept mounted through an
auth-refresh (e.g. a future non-full-screen refused state), a stuck
`busy=true` permanently disables every button in the catalogue (Refresh,
Rename, Mark complete, Delete, etc.) with no way to recover short of a
reload.

`handleSetStatus` already carries a `finally`-block comment describing the
EXACT same bug class, previously fixed there (Opus fresh-eyes, reproduced by
the version-prompt return) -- this bead applies the same fix to its two
remaining siblings that never got it.

## What shipped

`handleRename` and `handleUploadPdf` now reset `busy` in a `finally` block,
matching the shape (and citing the same rationale) as `handleSetStatus`.

Two new tests in `RemoteCatalogue.test.tsx`, one per handler: mock the
underlying API call to reject with `AuthError`, fire the action, and assert
the Refresh button (the simplest always-rendered `busy`-gated control) is
NOT left disabled once `onAuthError` fires.

Mutation-verified: reverting either handler's `finally` back to an
end-of-catch `setBusy(false)` reddened exactly that handler's new test
(and only that one), confirmed by running with `-t "auth error"` after each
mutation and restoring between them.

## Files touched

- `schema-editor/src/components/RemoteCatalogue.tsx` -- `handleRename` /
  `handleUploadPdf` reset `busy` in `finally`.
- `schema-editor/src/components/RemoteCatalogue.test.tsx` -- 2 new tests.
