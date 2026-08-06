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
(no extra per-kit fetch). The publish transition re-stamps from the GATE'S OWN
lint findings rather than re-linting -- a second lint run could only produce a
different answer than the gate just acted on.

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

Tests: backend 1620 passed (from a 1595 baseline -- 25 added, zero regressions),
schema-editor 1176 passed, typecheck clean. Six mutations verified across the
predicate, the fingerprint, the save path, and the render path.

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
