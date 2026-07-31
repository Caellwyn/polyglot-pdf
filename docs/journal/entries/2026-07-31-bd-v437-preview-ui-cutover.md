---
date: 2026-07-31
beads: [polyglot-pdf-v437]
tags: [frontend, pdf-view, schema-forms, feature-flag, cutover, ux]
surfaces:
  - frontend/src/pdf-view/viewMode.ts
  - frontend/src/schema-forms/components/SchemaForm.tsx
---

# Preview UI cutover: the `?previewUi=1` flag is deleted

## What happened

The maintainer asked why the PDF preview view was missing from the voice app UI.
It was not missing and not unfinished -- epic `polyglot-pdf-js7q` (closed
2026-07-09) shipped the whole dual-view surface, and the sprint-9 follow-up
epic `polyglot-pdf-oaiz` added click-to-edit on the PDF. Every one of those
surfaces was gated behind an opt-in flag (`?previewUi=1`, persisted in
sessionStorage) under an explicit hard constraint recorded in `featureFlag.ts`:

> HARD CONSTRAINT (maintainer 2026-07-06): every UI surface of the preview-mode
> epic renders ONLY when this flag is on. [...] Cutover (flipping the default) is
> a separate maintainer-gated change; do not flip it here.

That gate did exactly its job for three weeks -- and then outlived the memory of
why it was there. The feature was invisible because it was *supposed* to be, and
the only record of the opt-in was a comment in a module nobody had reason to
open. Worth noting for future default-off work: a flag whose discovery path is
"read the source" will read as a missing feature the moment the person who
approved it stops thinking about it.

The maintainer reviewed the preview view and approved cutover.

## What shipped

Flag REMOVED, not defaulted to true -- a flag pinned permanently on is dead
weight that every future reader has to evaluate.

- Deleted `frontend/src/pdf-view/featureFlag.ts` and its test.
- `SchemaForm.tsx`: dropped the `previewUiEnabled` state and all four gate sites
  (view toggle, Preview branch, "Preview Filled PDF" button, FilledPreviewModal).
- `viewMode.ts`: `initialViewMode(stored, viewportWidth)` lost its `flagOn`
  parameter.
- Tier-2 docs (`pdf-view.md`, `schema-forms.md`) rewritten to current state.

## The decision that was NOT made

Cutover made Preview **reachable**, not the **landing view**. A fresh mount with
no stored preference still starts in Simplified; mobile-width behavior is
untouched (starts Simplified, resize-into-mobile drops Preview).

This was put to the maintainer as an explicit choice, because it is a product
call and the epic plan listed "desktop default-mode decision" as out of scope.
The deciding factor was bug `polyglot-pdf-ks1y`: on the **i-90 kit that the live
demo runs**, 8 choice fields paint at the wrong rect, two of them ~108pt off --
a different row of the form. Triage on 2026-07-30 confirmed this is legacy
committed-kit data, not a pipeline defect (a fresh w7_v3 extraction has 0
mismatches), and the fix is a parallel `i-90_v2` extraction rather than an
in-place patch. Landing every user in Preview would put those 8 misplaced marks
in front of them; landing in Simplified means a user only sees the PDF once they
ask for it. Maintainer chose Simplified-first.

So Preview-as-default remains open, and `ks1y` is its natural precondition.

## What the review rounds found

Nine fresh-eyes rounds ran. Rounds 1-3 all found the same class: stale prose
asserting the deleted flag still gated something (comments in `SchemaForm.tsx`,
`pdf-view.css`, `pdfWorker.ts`, `PreviewPane.tsx`, the toggle's own stylesheet
header in `schema-form.css`, and a self-contradicting sentence in
`schema-forms.md`). All fixed. Lesson for the next flag removal: the flag's
NAME is easy to grep; the flag's PROSE is not. Sweep for "gated", "default-off",
"while the flag is off" across every file type, not just the module you think
owns the feature.

Round 4 found something users would actually hit. The mount-time mobile
demotion (`initialViewMode` forcing Simplified at <=768px) did NOT persist its
decision, while the resize-time demotion (`SchemaForm.tsx:182`) always has. So
state said Simplified while `sessionStorage['preview_view_mode']` still said
`preview`. Before the cutover this was unreachable -- no ordinary mobile user
could ever store `preview`, because the toggle never rendered for them. Making
the toggle always-on is exactly what made it reachable.

Fixed by persisting the demotion at mount, matching the resize path. Pinned by a
regression test that was confirmed to FAIL without the fix (`expected 'preview'
to be 'simplified'`) before being confirmed to pass with it.

Left undecided on purpose: mobile users can now reach the Preview surface at
all, which no prior round modelled and which has no mobile-specific styling.
That is a product call about whether phones should get Preview, not a flag-
removal question, so it is filed as its own bead (`polyglot-pdf-4hje`) rather
than settled here.

Round 5 produced the most transferable lesson of the whole change, and it is a
DOC trap rather than a code one. Refreshing this repo's tier-2 `*Last updated:*`
header lines is routine -- but that header had accumulated the ONLY record of an
invariant unrelated to this work (`help.instructions` / `help.details` /
`FormMetadata.details` / `booklet_text` are model-facing and must never render).
Collapsing the header to a clean current-state line silently deleted it, while
the guard test protecting it stayed live and green. **Before rewriting a
`*Last updated:*` line, diff the old one claim by claim and re-home anything
that is a real invariant into the doc BODY** -- a fact parked in a dated header
is one cleanup away from gone. (Restored here as a body paragraph in the
Rendering section, with the test's actual, narrower coverage stated honestly.)

Round 6 caught the tail of that same fix over-claiming: the restored paragraph
implied the guard test covers all four names when it only covers the two
field-level ones. Round 7 caught the same over-claiming ONE more level down --
the justification for deleting an inert test seed cited coverage that did not
exist -- and fixing it properly meant writing the missing test rather than
softening the sentence (see "Test notes" below). Three rounds in a row found a
doc/comment asserting stronger test coverage than the suite actually had; that
is the defect class this change kept producing, and it is worth watching for on
any review that touches test setup.

Rounds 8-9 found the same family once more, in the opposite direction: a doc
saying LESS than the code. `pdf-view.md` documented `initialViewMode`'s
resolution rule and spent nine lines on the symmetric RESIZE caller-contract
while saying nothing about the mount-time PERSISTENCE contract round 4 had just
added -- an asymmetry that reads as "mount has no such obligation," which is
exactly the belief that made round 4's bug possible. Added the missing contract
paragraph; round 9 then caught that paragraph stating the obligation more
NARROWLY than the shipped guard (`mode !== stored`, which also normalizes a junk
stored value), so a second caller conforming to the doc would still diverge from
SchemaForm. Widened to match the code.

Nine rounds is a lot for a flag deletion. Worth understanding why: the code
change itself was small and cleared early, but removing a flag invalidates every
sentence anyone ever wrote ABOUT that flag, and those sentences were scattered
across source comments, CSS headers, two tier-2 docs, and this journal entry --
each of which then had to be checked against reality rather than against what it
used to say. The recurring defect was never a bug; it was prose drifting from
the tree.

## Verification

- Full frontend suite: 71 test FILES / 273 suites / 1175 tests, 0 failures
  (re-run after every review round's fix, including the round-4 behavior fix).
  Note vitest's JSON reporter calls the describe-block count
  `numTotalTestSuites` (273) -- the file count is `testResults.length` (71),
  which is what the terminal's "Test Files" line shows. Quoting 273 as a file
  count would look like ~200 files had silently stopped collecting, which is a
  real failure mode in this repo (see the pool-drops-files scar).
- `tsc --noEmit`: clean.
- Bundle: verified on the **DEPLOYED** build -- `npm run build:schema:demo`
  (`vite.config.schema.ts`), which is what `deploy-demo.sh` actually runs;
  `deploy-production.sh` uses `build:schema`. Its entry chunk is
  `dist/assets/main-*.js`. (A bare `npm run build` uses the DEFAULT
  `vite.config.ts` and emits `index-*.js` instead, and is never deployed --
  `deploy-all.sh` warns it loads a `.env.production` with no `VITE_FIREBASE_*`
  keys, so the app dies at launch on `auth/invalid-api-key`. Check which config
  you ran before grepping; both were checked here and agree.) From a clean
  `dist/`, the entry chunk has ZERO `previewUi` / `preview_ui_enabled` and ZERO
  `pdfjs-dist` / `GlobalWorkerOptions`, with `schema-form__view-toggle`,
  `Form view` and `preview_view_mode` each present. pdf.js stays in its own lazy
  `pdf-view-*.js` chunk, which `index.html` does not modulepreload (the
  `React.lazy` boundaries are unchanged), so removing the flag did not pull
  pdfjs into the shipped entry bundle.
- Browser check reached the app shell but the form sits behind a Firebase
  sign-in wall; the unconditional-toggle assertion is instead pinned by a test
  that drives the real `SchemaForm` through React and reads the actual DOM.

## Test notes for the next person

Two suites needed care beyond a mechanical mock removal:

- `SchemaForm.previewEdit.test.tsx` exercises the Preview surface and used to get
  there via the flag mock. It now gets there by CLICKING the Preview tab in
  `mountInPreview()`, because Preview is no longer where a fresh mount lands.
  An earlier draft of this change ALSO seeded
  `sessionStorage['preview_view_mode'] = 'preview'` -- that seed was removed in
  review as dead weight: the click already lands in Preview, so the seed could
  never fail, and keeping it would have made the suite merely LOOK like it
  covered stored-preference-honoring. If you need the PDF surface in a new
  test, click the tab; do not re-add the seed.
- Removing that seed exposed a real hole (round 7). Nothing pinned the DESKTOP
  honoring direction at component level: `viewMode.test.ts` covers only the pure
  helper, and every `SchemaForm` test either cleared storage or asserted the
  mobile demotion -- so `getStoredViewMode()` could be deleted from the mount
  initialiser and all 1174 tests still passed (verified by sabotage). Added
  `honors a stored preview choice at desktop width`, confirmed to fail on that
  sabotage (`expected 'false' to be 'true'`) and pass on the real code. General
  lesson: when you delete a test's setup as inert, check whether the contract it
  APPEARED to cover is pinned anywhere else -- "inert here" and "covered there"
  are different claims.
- The continuous-mode paging suite used `isPreviewUiEnabled -> false` to force
  the Simplified view. That intent survives on `sessionStorage.clear()` alone,
  since Simplified is still the no-preference default -- but it is now implicit,
  so the comment there spells it out.
