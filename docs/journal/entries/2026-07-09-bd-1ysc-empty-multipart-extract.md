---
date: 2026-07-09
bead: polyglot-pdf-1ysc
title: "Hosted Run-extraction 400'd on an empty multipart body"
tags: [schema-editor, extraction, bugfix]
---

## Trigger

Maintainer hit it live (with screenshot): clicking Run extraction in the hosted
editor showed "There was an error parsing the body" and the extraction never
started. Contractor-blocking: onboarding a new form without an instructions PDF
was impossible.

## Root cause (reproduced locally)

`extractRemoteKit` (schema-editor/src/utils/remoteKitStore.ts) POSTs
multipart/form-data to `/api/editor/kits/{kit}/extract` but only appended
`force` when truthy and `instructions_pdf` when attached -- so the bare
Run-extraction click sent a COMPLETELY EMPTY FormData (a body that is just the
closing boundary). python-multipart 0.0.9 rejects that with
`MultipartParseError` ("Did not find CR at end of boundary"), which is NOT a
starlette `MultiPartException` subclass, so starlette's form handler does not
catch it; FastAPI's blanket handler turns it into 400 "There was an error
parsing the body" BEFORE the route body executes. The client surfaces the
detail verbatim. Attaching an instructions PDF "fixed" it because the body was
non-empty -- which is why the bug survived: unit tests mocked extractRemoteKit
and never did a real multipart round-trip.

## Fix

One line: `extractRemoteKit` now ALWAYS appends `force` ('true' or 'false') so
the multipart body is never empty. Verified against the REAL route (TestClient):
- `force=false` multipart -> past body parsing (404 "Unknown kit" for a fake
  kit -- i.e. into route logic), and FastAPI coerces the string to boolean
  False (no accidental force-re-extraction).
- The old zero-part body -> the exact 400 (kept as the demonstration).

Regression test (`remoteKitStore.test.ts`): the bare call's FormData contains
`force=false`; force:true sends 'true'; the instructions PDF still attaches
alongside. Full schema-editor suite green (36 files).

## Deliberately deferred

Backend-side hardening (tolerating an empty form body on the route, or mapping
the parse error to a friendlier detail) -- the client fix eliminates the case
from our client; a non-browser caller sending a zero-part body would still get
the opaque 400. Noted on the bead; low priority.
