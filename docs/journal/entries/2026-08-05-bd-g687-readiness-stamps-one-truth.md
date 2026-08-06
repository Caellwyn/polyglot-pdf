---
date: 2026-08-05
bead: polyglot-pdf-g687
title: "s18 C4: one truth for progress in both modes (readiness stamps)"
sprint: 18
tags: [schema-editor, refactor, testing]
---

## Trigger

Third child of the sprint-18 editor-UX epic (polyglot-pdf-4qul, plan
docs/sprint_18_editor-ux-overhaul_plan.md decisions 2 + 4, rubric 1's catalogue
half), unblocked by C1 (o7y9) and the catalogue-drift fix (q3rm, PR #547).

C1 pinned ONE count predicate for the open kit, and q3rm routed both catalogue
scans through it -- but "how much of this kit is reviewed?" still had only a
CLIENT-side answer, recomputed by whichever surface asked last. That is the seam
behind the epic's founding symptom: a confident 100% strip sitting beside a 409
publish refusal. The kit's progress needed a recorded, server-computed answer.

## What shipped

**One backend definition.** New backend/services/publish_readiness.py answers
"how much has a human reviewed, and may this publish?" A field counts reviewed
exactly when it carries a sign-off, has no lint ERROR, has a CURRENT guidance
ack, and has no finding newer than the sign-off. The ack is checked NATIVELY --
the server calls guidance_contract.identity_sha1 directly rather than parsing
the hash out of a lint-finding path -- so there is no cross-language copy of
the hash rule.

**The fingerprint mirror.** The timeliness rule compares against
_review.seen_fingerprints, which the CLIENT writes, so the Python fingerprint
must be byte-identical to lintFindings.ts findingFingerprint -- including the
content discriminator's UTF-16 code-unit iteration and 32-bit signed
wraparound. Nine parity cases were captured by RUNNING the real TS
implementation and are pinned as byte comparisons, plus a guard that fails if
the client's MESSAGE_LOCALIZED_RULES set grows without the mirror following.

**Stamps.** The hosted save and the status flip record the counts into
metadata.json; the /kits listing returns the stamp on metadata it already reads
(no extra per-kit fetch). The publish transition RE-LINTS the schema it is
about to publish rather than reusing the gate's findings: the translation drift
sweep runs AFTER the gate and mutates + re-persists the schema, so the gate's
findings describe a different object than the one being stamped. (An early
draft of this bead did reuse them, which stamped pre-sweep counts under a
post-sweep hash -- an internally inconsistent stamp the editor contradicted on
open. Both the stamp and that re-lint choice are now test-pinned.)

**Both catalogues read stamps.** Hosted and local-folder cards render the stamp
or, when it is absent / unverified / stale, a plain-language verify hint --
never a fall-back re-scan. Local mode reads the same metadata.json the backend
wrote, so both modes share one definition. readinessStamp.ts owns the single
"may I show this number?" rule.

Two maintainer decisions taken at claim time, recorded as a scope amendment on
the bead:

1. **publish_readiness ownership split with C2.** Both beads named the file, and
   this bead's exit criterion 2 required the GATE to call it -- but the gate
   refusal is C2's slice, and C2 is blocked behind this bead. Decision: C4 builds
   the function and the stamp; C2 wires the gate to the SAME function. Criterion
   2 is amended accordingly; nothing here introduces a second definition for C2
   to inherit.
2. **No re-scan fallback.** An unstamped kit shows the hint, never a recomputed
   percentage. Accepted consequence: every existing kit shows the hint until it
   is next saved, since no kit carried a stamp before this shipped. The
   alternative (fall back to a scan) would reintroduce exactly the
   two-sources-of-truth bug q3rm just fixed.

The bead's third instruction -- "getCompletionStats gains an errors bucket" --
was obsolete on arrival: q3rm deleted that function hours earlier. The intent
(an errors count plus a test-pinned counting invariant) carries to
ReadinessCounts instead.

**The assess round found four ways "one definition" was not yet true**, all
real and all fixed in-loop:

1. The compact catalogue STRIP -- the DEFAULT view -- still read the local disk
   re-scan in both catalogues, so the dropdown could print a client-recomputed
   number while the card below it showed the verify hint. Only the expanded
   cards had been converted.
2. Percentage ROUNDING diverged across the mirror: Python's round() is banker's
   rounding while the client's Math.round ties up, so an exact .5 ratio stamped
   one number and displayed another (1 of 8: 12% stamped, 13% shown). The
   backend now matches JS semantics, pinned on both sides with one ratio table.
3. The client's hasUncoveredStructuralError clause had no Python equivalent --
   despite reviewStatus.ts's own docstring saying the server computes the
   identical clause. A choice field whose options name no PDF widget counted
   REVIEWED in the stamp while the editor rendered it red. Now mirrored.
4. The publish path's stamp was UNGUARDED while the save path's was wrapped. By
   the time it runs the kit has cleared every gate and the translation sweep may
   already have written re-translations, so an exception would 500 a legitimate
   publish and leave the caller retrying a partly-completed transition.

**A second (Opus) assess round found the mirror STILL diverged**, on a
reachable everyday flow, plus four smaller issues:

5. THE BUG. The Python timeliness rule did not exclude guidance-identity-stale,
   but the client's newFindingsSinceReview does -- with a comment recording an
   earlier review that found why: the ack gate is that rule's SOLE owner, and
   the ack writer preserves seen_fingerprints, so counting the stale finding in
   BOTH places makes sign-off -> drift -> ack a dead end no control can clear.
   Measured on identical input: Python False, TypeScript True. One saved kit,
   two numbers -- this bead's own bug, recreated inside the mirror. It would
   also have poisoned C2, whose gate would refuse BY NAME a field the editor
   renders green.
6. The publish stamp reused the GATE's lint findings, but the translation drift
   sweep mutates and re-persists the schema after those were computed -- so the
   stamp recorded pre-sweep counts under a post-sweep schema hash. It re-lints
   now.
7. readKitProgress still computed a percentage nothing rendered (its
   RemoteCatalogue twin had been nulled for exactly this reason) -- a live
   second definition of the centralized number, which is how a fallback creeps
   back.
8. Three docstrings claimed an out-of-band-edited kit "reads as stale, not as
   truth". False as written: no caller passes readStamp's currentSchemaSha1, so
   that branch is unreachable in production. Corrected, with a pointer to the
   bead that will make it true (polyglot-pdf-j8sr).

**The OUTER review then found three more** that eight inner rounds had missed,
all in the same blind spot: the inner loop kept checking the two stamp parsers
for VALUE mismatches and never for SHAPE ones. A stamp missing `ready` made
Python drop the whole stamp while the client kept it and rendered a percentage;
`percent: 75.0` (what any jq or Python round-trip of the stamp produces, since
JSON has one number type) parsed on the client and not on the server; and BOTH
parsers accepted `percent: 999`, which the card renders as a bar WIDTH. Fixed
on both sides and re-probed against both real implementations.

Two further out-of-scope bugs came out of that review and are filed:
polyglot-pdf-dm3c8 (the verdict's `ready` flag ignores SCHEMA-LEVEL lint
ERRORs, so it reads True for a kit /status will 409 on -- latent because
nothing reads `ready` yet, and now a HARD BLOCKER on C2/polyglot-pdf-apmo,
which is exactly where it would go live) and polyglot-pdf-kwh3t (a corrupt
acroform.json degrades to a dump-blind lint that still stamps verified:true,
where the /lint route deliberately 502s on the same condition).

Filed rather than widened into this bead: polyglot-pdf-j8sr (five routes
rewrite a schema without re-stamping; local-folder save never stamps),
polyglot-pdf-drpn (every save now rewrites metadata.json, widening a
pre-existing concurrent-write revert window), polyglot-pdf-lu1i and
polyglot-pdf-93p8 (client/backend predicate divergences on inputs the current
lint emitter cannot produce; 93p8 supersedes the earlier polyglot-pdf-wjes,
which should close as a duplicate when 93p8 is worked), and polyglot-pdf-evt9
(/label and /status destroy an unparseable metadata.json the same way the save
path did -- pre-existing, and found because C4 fixed that shape on its own new
writer, leaving the asymmetry visible). polyglot-pdf-eh2i was filed against
this bead's parity harness and is FIXED here, so it closes with this PR.

**The assess loop ran EIGHT rounds** (4, 8, 7, 3, 5, 7, 4 findings, then
NO-GAPS) -- every round because its findings were correct and blocking, not
because of thrash. Beyond those already listed:

- a stamp could HIDE a schema-corruption notice (the notice was gated on the
  percentage being absent, which stopped being true once the percentage came
  from the stamp);
- `bool()`/`int()` coercions let a hand-edited stamp read differently in hosted
  vs local mode -- `bool("no")` is True, so a string flipped the honesty bit on;
- the whole publish-path stamp, and separately the publish RE-LINT decision,
  could each be deleted with the entire backend suite green;
- a save over a kit whose metadata.json was UNPARSEABLE replaced the file with
  just the stamp, deleting its status and label. Pre-C4 the save wrote no
  metadata at all, so this diff had made an ordinary Cmd+S destructive;
- and the FIX for that over-corrected: it skipped whenever load_metadata
  returned None, but None means absent OR unparseable, so a kit with no
  metadata.json (form-kits/w9-heldout ships that way) could never be stamped.

Three recurring shapes, recorded in Lessons: fixing one half of a mirrored pair
(strip vs card, hosted vs local, Python vs TS); tests that describe rather than
pin; and comments that over-claim what the code guarantees.

Final tests: backend 1676 passed (from a 1595 baseline, zero regressions),
schema-editor 1210 passed, typecheck clean. ~25 mutations verified across the
predicate, the fingerprint, the rounding (both sides), the structural clause,
the stale-rule exclusion, both stamp call sites, the publish re-lint, the
listing, both parsers, the metadata-preservation branches, and every render
path. The final round additionally fuzzed the fingerprint mirror over 4,000
randomized inputs and proved the rounding mirror exhaustively (80,199 pairs).

## Lessons

- **A test whose fixture makes the bug's output look like the correct output
  will survive the mutation.** The unstamped-kit test used an unreviewed
  fixture, so a restored re-scan fallback computed 0% -- indistinguishable from
  "no number rendered," and the mutation passed. Changing the fixture to a
  FULLY REVIEWED schema made the fallback produce a loud 100%, and switching the
  assertion from blacklisting one value to rejecting the whole /^\d+%$/ class
  made it catch. Choose the fixture so the bug is LOUD, not merely present.
- **A mutation that changes a value nothing reads is a no-op, not a passing
  test.** The first attempt at the fallback mutation edited the scan's returned
  percentage -- but the render path no longer consults it, so nothing could have
  failed. Mutate the line that actually governs the property (here, the render
  precedence), or the round proves nothing.
- **An existing test caught a real robustness bug in new code.** The stamp
  helper originally caught only FormKitStoreError, so any other store failure
  (an AttributeError from a store without put_metadata) would have turned a
  SUCCESSFUL save into a 500 the editor reports as "save failed." The schema is
  already written when the stamp runs, so the whole failure class must be
  swallowed. Pinned with its own regression test.
- **"Test-pinned" must mean a SHARED expectation, not two per-side test
  suites.** The module docstring claimed the mirror's equality was test-pinned;
  only the FINGERPRINT actually was. Both sides' unit tests passed green while
  the predicates returned different answers for the ordinary ack flow, because
  each suite asserted what its own implementation did. The fix is structural: a
  shared fixture (`__fixtures__/reviewPredicateParity.json`) both suites execute
  against their real predicate, so changing either side alone breaks a test.
  Reach for this the moment the SAME rule exists in two languages -- per-side
  tests cannot detect divergence by construction.
- **When mirroring a function, read its comments for rules that are not in its
  signature.** The stale-rule exclusion existed only as a filter inside
  `newFindingsSinceReview` with a comment explaining a dead-end it prevented. I
  mirrored the clause list from the docstring and missed a rule that lived in
  the body -- and that omission recreated the very bug the module exists to
  prevent. A prior review had already paid for that lesson once; the comment was
  the record, and I did not read far enough.
- **A cross-language mirror diverges at the EDGES, not the core.** The
  fingerprint -- the scary part, with UTF-16 and 32-bit wraparound -- was
  correct, verified against nine cases run through the real TS. What actually
  diverged was mundane: the ROUNDING MODE of a percentage (Python ties-to-even
  vs JS ties-up) and a whole missing clause. When claiming two implementations
  agree, enumerate every observable output of both (not just the interesting
  one) and pin each with the SAME table on both sides.
- **An asymmetry between two call sites of the same helper is a finding in
  itself.** The save path guarded its stamp; the publish path did not. Nothing
  failed, but the inconsistency was the tell -- and the unguarded one sat behind
  more already-committed work (a written translation sweep), so it was the more
  dangerous of the two.
- **A worktree's node_modules must be a real Windows JUNCTION, not a POSIX
  symlink.** A bash-created symlink let `tsc` and single-file runs appear to
  work while vitest's forks runner timed out with "Timeout starting forks
  runner" / "no tests" -- for ~40 minutes, looking like a wedge to clear rather
  than a broken link. The tell: the SAME test file passed from the main checkout
  and failed from the worktree. mklink /J fixed it. (Extends the existing
  frontend-tests-in-worktrees memory: verify the link TYPE, not just that
  node_modules resolves.)

## Doc freshness

The freshness checker's verdict at closeout governs; the stale docs it reports
track voice/backend surfaces this branch did not touch. No tier-1/2 doc
describes the catalogue percentage or metadata.json's shape by name -- the
plan + this entry are the record. docs/sprint_18_editor-ux-overhaul_plan.md
line 252 still describes the deleted getCompletionStats (tracked as bd
polyglot-pdf-ipci, filed during the q3rm review).

## Files touched

- backend/services/publish_readiness.py (new) -- THE definition + fingerprint mirror
- backend/routes/editor_kit_routes.py -- stamp helpers, save/status wiring, /kits exposure
- backend/tests/unit/test_publish_readiness.py (new) -- 24 tests, 4 mutations
- backend/tests/unit/test_editor_kit_routes.py -- stamp assertions, save-survives-stamp-failure, status byte-stability
- schema-editor/src/utils/readinessStamp.ts (new) + its tests -- the "may I show this number?" rule
- schema-editor/src/utils/remoteKitStore.ts, formKitDirectory.ts -- the shared stamp type, local parse
- schema-editor/src/components/RemoteCatalogue.tsx, FormCatalogue.tsx (+ tests) -- stamp-or-hint rendering
