---
date: 2026-08-13
bead: polyglot-pdf-tqr3c
title: "Local extraction unusable: sibling-worktree reloads dropped the request, and exit-3 drafts were deleted"
sprint: null
tags: [schema-editor, extractor, harness, testing]
---

## Trigger

Maintainer hit `Extraction failed for "i-90_v2": Failed to fetch` in the local
schema editor. Fixing that surfaced a SECOND, independent defect behind it:
`extraction failed (exit 3): WARNING: the draft did not validate`. Both are
local-vs-hosted drift -- the class of bug `run-schema-editor.sh` starts the real
backend specifically to eliminate.

## Defect 1 -- a bare `--reload` watched ~130 sibling worktrees

`Failed to fetch` is a browser TRANSPORT failure, not an extractor error: the
request left the browser and the dev server never completed the response. The
tell that the extractor was not at fault is that a real extractor failure
returns readable JSON (`extraction failed (exit N)`), and that the Extract
button was VISIBLE at all -- `isExtractionAvailable()` hides it unless
`GET /api/extract` already succeeded.

Both launchers ran `uvicorn backend.main:app` with a bare `--reload` and cwd at
the repo root. A bare `--reload` watches the WHOLE cwd tree, and the repo root
holds `.claude/worktrees/` with ~130 full checkouts. So an agent editing any
`.py` in ANY worktree restarted this backend. `run-schema-editor.sh` runs under
`set -e` with a `trap 'stop_backend' EXIT INT TERM`, so a non-zero backend exit
tears down the WHOLE launch -- Vite included -- dropping the in-flight POST
`/api/extract`. That request runs for MINUTES (it spawns `extract_form.py` plus
the `claude` CLI), so the window is wide. Worse, `extractEndpoint`'s
`res.on('close')` handler fires `killTree` on any dropped connection, so the
blip did not merely lose the response -- it destroyed the (paid, minutes-long)
extraction run.

Fix: `--reload-dir backend` in both launchers, plus
`server.watch.ignored: ['**/.claude/worktrees/**']` in the editor's Vite config
as defence in depth. Scoping to `backend/` is safe -- verified that `backend/`
imports no other top-level package (`shared/` is a single JSON file with no
Python at all).

**Note the editor and the main app share ONE backend.** Both launchers run the
same `backend.main:app`; there is zero Python under `schema-editor/`, and the
editor's server routes live in `backend/routes/editor_*.py`. So
`--reload-dir schema-editor` would have watched a directory with no Python and
silently never fired -- see the near-miss below.

## Defect 2 -- exit 3 means STORE, and this endpoint deleted

With transport fixed, extraction ran to completion and returned exit 3. That is
not a crash: `extract_form.py` defines a tri-state exit code where
`EXIT_ISSUES = 3` means "a usable draft was written (>= 1 field) but it is
invalid and/or carries lint ERRORs: **STORE it with its issue report**". The
hosted route honors exactly that (`editor_kit_routes.py`, bd v96b) -- it stores
the draft and returns `storedWithIssues`.

The dev endpoint did not: `const ok = code === 0` sent exit 3 into the failure
branch, which ran `cleanupTmp()` and deleted the draft it had just produced. On
i-90_v2 that discarded **141 well-formed fields** over **7 lint errors**, all of
them the same rule (`to-review-pending`) on the same kind of field: the 2D
barcode widget USCIS puts on each page (`barcode_p1`..`barcode_p7`), parked in a
holding section awaiting a human decision. That decision is precisely what the
editor exists to make -- so the endpoint was throwing away the artifact the user
opened the editor to fix.

Fix: store an exit-3 draft, matching hosted. Usability is re-derived from the
WRITTEN draft (parseable, >= 1 dict-shaped field) rather than trusting the exit
code, mirroring the hosted route's floor so a mis-exit can never store garbage.
The response carries `storedWithIssues` and leads its detail with "stored with
issues", so a draft with problems never reads as a clean pass.

## Near-miss worth keeping: a scoped watcher that was actually DEAD

The first verification of defect 1 used only a NEGATIVE control -- edit a file in
a sibling worktree, observe no reload -- and it "passed". It was wrong. Adding
the POSITIVE control (edit a file under `backend/`, which MUST reload) showed
nothing happened there either: that reload had killed the reloader process,
leaving a worker still serving `/health` with no watcher behind it. A watcher
that ignores everything trivially passes a negative control.

**A negative control alone cannot distinguish "correctly scoped" from "dead".**
Re-ran both controls against one live watcher: `backend/` edit reloads, sibling
worktree edit does not. Only then was the claim earned.

## Verification

- Real extraction of i-90_v2: `ok:true`, HTTP 200, `storedWithIssues:true`,
  `schema.json` persisted (141 fields; 7 `to-review-pending` ERRORs, 17
  warnings). Previously this exact file was created and then deleted.
- Watcher: both controls on one live watcher (above).
- `tsc --noEmit` clean; schema-editor suite green; backend suite 3071 passed /
  3 skipped on the dev-merged tree.

## Follow-ups filed

- **polyglot-pdf-ysn61** -- `extractEndpoint.test.ts` has 28 tests and NONE reach
  the spawn (the file's own header says so), so the entire result path is
  untested. This change stayed fully green through both defect and fix; the only
  real evidence was an end-to-end extraction. Bead carries the cases to add and
  the mutations that must redden each.
- **polyglot-pdf-m5ijv** -- EPIC: extract the schema editor into a standalone
  product (own repo, own deploy, separately shippable), filed at the maintainer's
  request during this work. Carries the measured coupling map. Needs `/plan-epic`
  before any code moves.
