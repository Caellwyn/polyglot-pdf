---
date: 2026-07-06
bead: polyglot-pdf-fgdo
title: "De-flake App.hosted 'Escape closes the guide' (effect-timing race)"
tags: [testing]
---

## Trigger

Found during the wave-3 batch verification (bd polyglot-pdf-432u): the
schema-editor test `App.hosted.test.tsx > "Escape closes the guide and persists
the dismissal"` failed ~1 run in 3, even in ISOLATION, independent of any source
change. Filed as its own bead; this is the fix.

## Root cause (verified, not assumed)

NOT an async-unmount race (my first guess -- a `waitFor` around the removal
assertion did NOT fix it, still 4/10 failing). Capturing the actual failure
showed the dialog was STILL PRESENT after Escape -- i.e. the Escape keydown
never triggered the close handler at all on the failing runs.

The real cause: `HostedGuide` (schema-editor/src/components/HostedGuide.tsx:62)
attaches its Escape keydown listener in a `useEffect`, which runs AFTER the
dialog is queryable in the DOM. The test did `getByRole('dialog')` (passes once
the dialog is rendered) and then IMMEDIATELY `fireEvent.keyDown(window, Escape)`
-- but on the runs where the effect had not yet flushed, no listener was
attached, so the Escape was dropped and the guide never closed.

## Fix

Re-fire Escape INSIDE a `waitFor` so it retries until (a) the listener is
attached and (b) the resulting `setGuideOpen(false)` re-render unmounts the
dialog. An extra Escape after the guide is gone is a harmless no-op. Pure
test-only change; `HostedGuide`'s behavior is correct and unchanged.

## Verification

The previously-flaky test now passes 12/12 consecutive isolated runs (was ~1/3
failing); the full `App.hosted.test.tsx` (19 tests) passes 3/3.

## Doc freshness

None -- test-only.
