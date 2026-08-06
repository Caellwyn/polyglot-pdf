---
date: 2026-08-06
bead: polyglot-pdf-w3zw
title: "Kit revision archive on republish + audit-schema retrieval"
sprint: 19
tags: [testing, conventions]
---

## Trigger

Sprint 19 (docs/sprint_19_firm-tier-kit-lifecycle_plan.md), epic
polyglot-pdf-7jmy child 1 of 4 -- the first implementation bead of the kit
lifecycle epic, and the one the rest of the chain is blocked behind.

Kit storage is ONE slot per kit_id with overwrite-in-place, while the
confirmation audit trail (bd 47r3) records kit_id + a revision marker. A marker
is not a storage address, so republishing a kit destroyed the schema its
earlier confirmation records were confirmed against: the trail could name a
revision the store could no longer produce, and "what did field p1_line3a ask?"
became unanswerable. Epic rubric #2 is exactly that retrieval.

## What shipped

- **Store primitives** (`backend/services/form_kits.py`): `put_archived_revision`,
  `load_archived_revision`, `list_archived_markers` on `FormKitStore` with local
  and GCS implementations, reusing the existing atomic temp+replace write and
  the FormKitNotFound-vs-FormKitStoreError wrapping discipline. Archives live at
  `<kit_id>/_archive/<marker>/`.
- **`encode_marker`**: a kit-controlled marker becomes a path segment, so it is
  untrusted like a filename -- but it cannot go through `safe_filename`, because
  real markers contain characters that guard rejects (the "/" in a "12/2024"
  edition date, the ":" in a `sha256:` fingerprint). It ENCODES rather than
  rejects so every marker round-trips, and collapses dot runs so no literal ".."
  survives in a stored name.
- **The archive hook** (`backend/routes/editor_kit_routes.py`) on the
  revert-to-draft transition, resolving the marker from the superseded
  revision's own schema via the existing `resolve_edition_marker`. Best-effort:
  a failure logs loudly and never blocks the revert.
- **`scripts/read_kit_revision.py`**: operator retrieval by kit_id + marker,
  returning the current schema when the marker still matches it, else the
  archived copy. Keeps "absent" (exit 1) distinct from "store unreadable"
  (exit 2), the read_confirmations.py lesson from bd z2is.
- 24 test functions / 29 cases (one is parametrized over marker shapes),
  mutation-verified; full backend suite green.

**Hook placement deviates from the plan, deliberately.** The plan said to
archive "on promotion to complete". That is too late: a published kit's schema
cannot be written while status is complete, so the only route to a new revision
is complete -> draft -> save -> complete, and by promotion time the superseded
bytes are already overwritten. The archive fires on the revert instead -- the
last moment the published revision exists. The plan's INTENT (superseded
revisions stay retrievable) is unchanged; only the location moved.

**That premise was HALF TRUE when first written, and the review caught it.**
Fresh-eyes scored exit criterion 1 FAIL on two counterexamples, both fixed here:

- `extract_editor_kit` had NO complete-status gate, so
  `POST /kits/{id}/extract?force=true` could overwrite a published kit's schema
  in place, bypassing the archive entirely. I had counted five `== "complete"`
  gates and concluded "every editing route refuses" -- a count of GATED sites is
  not proof that all sites are gated, and the extract route was the seventh
  `put_schema` caller with no gate. Fixed by adding the same 409 the other write
  routes use.
- The idempotence check skipped on the marker NAME being taken, so two different
  revisions sharing one `edition_date` (an author edits fields without bumping
  the government edition string) meant the second was dropped and retrieval
  returned the FIRST revision's schema -- a WRONG answer, worse than a missing
  one for a legal record. Fixed: skip only when the archived copy IS this
  schema; a distinct revision under a taken marker archives under a
  fingerprint-disambiguated sibling so both survive.

**Round 2 then found the write-side fix had MOVED the bug to the read side.**
A confirmation record carries the PLAIN marker, but the second colliding
revision now lives under `<marker>--<fingerprint>` -- and retrieval did one
plain-marker lookup, so a record naming the second revision silently got the
FIRST one's schema, exit code 0. The same "confident wrong answer" defect,
relocated. Fixed: `_resolve` collects EVERY stored revision answering to the
marker (live schema, plain segment, and any sibling), returns the one when
there is exactly one, and raises `AmbiguousRevision` (exit 3) when there are
several -- it never picks. `--segment` reads one exact archived segment for the
operator who has disambiguated from `--list`. Identical bytes under several
segments count as one revision, not an ambiguity.

**The Opus clearing round found the leak every Sonnet round missed:** archived
revisions reached the PUBLIC Hosting bundle. The two runtime catalogues exclude
`_archive` structurally, but `copyKitsToPublic` is a blanket recursive `fs.cp`,
and the deploy scripts' `_*` guards skip only TOP-level entries (which is why
`form-kits/_translation` is safe and a nested `_archive` was not) -- so every
superseded schema became fetchable at
`/form-kits/<kit>/_archive/<marker>/schema.json`. The reviewer filed it rather
than blocking, on the grounds that the fix lands outside this bead's declared
surfaces; I folded it in instead. Publishing a legal-retention artifact to an
unauthenticated origin is a DIRECT consequence of this diff creating `_archive`,
and the fix is a one-line `filter` on the copy. Shipping the cause and deferring
the exposure would have been the wrong trade. The GCS upload deliberately still
carries archives -- that bucket IS the authenticated store the operator read
goes through. Doc wording narrowed to "runtime catalogues", which is what the
structural guarantee actually covers.

**A later Opus pass put criterion 1 back to FAIL on two more, both fixed:**
(a) the sibling was built as `f"{marker}--{fingerprint}"` from the RAW marker
and truncated afterwards, so a long `edition_date` (unbounded free text) cut the
fingerprint off -- at >=128 chars the sibling encoded IDENTICALLY to the base
and the second revision OVERWROTE the first on disk, with retrieval then
returning the wrong schema and the original gone (worse than the pre-bead state
for that kit); just under that the mangled suffix stopped matching the reader's
pattern, making the sibling invisible. Fixed with `sibling_marker`, which
budgets the fingerprint FIRST and trims the base around it, pinned by a test
parametrized over eight marker lengths. (b) the script's stdout was not
machine-readable -- structlog defaults to stdout, so the documented
`> revision.json` workflow produced an invalid file while exiting 0, defeating
criterion 1's own "diff clean" check. Fixed by binding structlog to stderr
before the store is constructed. Also fixed rather than deferred: the AMBIGUOUS
message told operators to compare "each revision's archived metadata" while
offering no way to read it -- it now prints each candidate's `published_at`
beside a copy-pasteable `--segment` command.

**And the next Opus pass caught the other half of that fix.** `sibling_marker`
trims the base to fit the fingerprint, but `_resolve` held the UNTRIMMED base
and required an exact prefix -- so every sibling of a marker >=108 chars was
invisible to retrieval, which returned the other revision at exit 0 with no
ambiguity report. The data-loss band was closed and the wrong-answer band had
simply moved (115-127 -> 108+). `_is_sibling_of` now accepts a stored base that
is a PREFIX of ours (the fingerprint suffix is still validated exactly, so the
round-3 false-ambiguity protection holds -- verified against all five prefix
cases). It also found that the length-parametrized test could not have caught
this; see Lessons 6.

**And that fix over-corrected into a WORSE bug.** Accepting any prefix made a
revision published under "12/20" answer to a record naming "12/2024" -- an
unrelated schema returned at exit 0, where the false negative it replaced at
least returned a real revision of the right marker. A shorter stored base is
now accepted ONLY at the writer's exact trim budget (reconstructed from the
same `_MARKER_MAX_LEN` the writer uses, imported rather than copied), which
admits every genuine trimmed sibling and rejects the impostor. The suite had
no two markers in a prefix relationship, so that whole dimension was unpinned;
it now has direct and end-to-end cases in both directions. Two adjacent
fragilities fixed alongside: `sibling_marker`'s 8-char base floor could emit a
segment longer than the cap it budgets against (failing on exactly the
pathological fingerprint it was written for), and the `rfind("--")` split is
now pinned by a round-trip parametrization over markers containing dash runs.

**Round 3 cleared all three criteria** and found one last defect in that fix:
sibling matching used `startswith(f"{base}--")`, which INFERS the relationship
from the segment's name. `encode_marker` collapses any run of unsafe characters
to one `-`, so an unrelated marker like `12/2024//rev2` encodes to
`12-2024--rev2` and looked like a sibling of `12/2024` -- a FALSE ambiguity
between two unrelated revisions, which erodes the exit-3 signal the tool depends
on. Fixed by matching the suffix's real shape (an encoded `sha256:<12hex>`
fingerprint) instead of any `--` run, with a test pinning the coupling to
`resolve_edition_marker`'s format so the two cannot drift apart silently.

## Lessons

1. **A helper-level test suite can be fully green with the feature unwired.**
   Four mutations were run. Three were caught. The fourth -- deleting the
   archive call from the status route entirely -- left ALL 17 tests passing,
   because every test called `_archive_published_revision` directly and none
   drove the route. Two tests over the real HTTP endpoint fixed it. This is the
   existing "verify the mutation that MATTERS, and drive the real entry point"
   scar tissue, hit again in a new shape: the tempting mutation (break the
   logic) was caught, while the likely regression (drop the call) was not.
   Generalizable rule already in docs/standards/testing.md's mutation guidance;
   this entry is the second instance.
2. **Check the neighbouring test file's helpers before copying one from
   elsewhere.** The new file's `_run` used `asyncio.get_event_loop()`, which
   passes in isolation and fails once another file closes the loop -- 19
   failures in the full suite after a clean isolated run. `test_editor_kit_routes.py`
   sits beside it and already documents the fix (bd polyglot-pdf-r8gq) in a
   comment on its own `_run`. The DeprecationWarning was visible in the very
   first green run and I did not act on it.
3. **"I checked N sites and they all had the guard" is not the same claim as
   "every site has the guard".** The archive's whole design rested on a
   universal: no route writes a published kit's schema. I verified it by
   counting the gates I found (five) rather than by enumerating the WRITE SITES
   and checking each (seven). The two extra sites were the actual answer, and
   one of them was the hole. Enumerate the population, then check coverage --
   the same "enumerate the block, don't hand-list it" lesson in a control-flow
   shape. The regression test now pins the PROPERTY (every schema-writing editor
   route refuses a published kit) rather than the one route that was missing it,
   so a newly-added write route must gate or fail.

4. **Fixing a write path can relocate the bug to the read path.** Round 1: two
   revisions collided on one marker and the second was destroyed. The fix made
   the WRITE side store both -- under a new sibling key. Round 2: retrieval
   still looked up only the plain marker, so the record that meant the second
   revision now got the first one's bytes. Same defect ("a confident wrong
   answer"), same severity, one layer over. The lesson is to re-ask the ORIGINAL
   question of the whole round trip after a fix, not just of the code that
   changed: "can a record still resolve to the wrong schema?" would have caught
   it immediately, where "is the write correct now?" did not. Where a key can
   genuinely be ambiguous, the honest answer is to REFUSE (exit 3) rather than
   return the nearest match.

5. **Don't infer a structural relationship from a string's shape when the
   encoder is lossy.** The sibling test asked "does this segment start with
   `<base>--`?", but `encode_marker` maps many raw markers onto the same shape,
   so unrelated names answered yes. Matching the suffix's ACTUAL format (an
   encoded `sha256:<12hex>`) is what makes the question answerable -- and
   because that couples two modules, a test now pins the format rather than
   leaving them to drift. Same family as the round-1 lesson: verify the
   property, don't infer it from a proxy.

6. **A parametrized test can certify a broken band as green when an unrelated
   candidate satisfies the assertion.** The marker-length test asserted that
   retrieval raises `AmbiguousRevision`, and it passed at every length -- but
   the LIVE schema also answered to the marker, so it supplied a second
   candidate by itself. Ambiguity was raised whether or not the sibling was
   ever found, so the assertion held while siblings were invisible from 108
   chars up. Parametrizing the length dimension was necessary and not
   sufficient: the fixture has to ISOLATE the thing under test (move the live
   schema out of the candidate set) and assert on the CANDIDATE COUNT, not just
   that the exception fired. Corrected, the same test fails at 114-300 and
   passes at 10/60 -- which is what "mutation-verified" has to mean.

7. **Fixing a write path can leave the matching read path broken at the same
   inputs.** This is lesson 4 recurring one layer deeper: the truncation fix
   made both revisions survive on disk, and the band where retrieval could not
   SEE the second one merely shifted (115-127 -> 108+). After any fix to a
   round-trip, re-ask the original question of the whole round trip -- "can a
   record still resolve to the wrong schema?" -- not just of the side that
   changed.

8. **Loosening a match to fix a false negative invites a false positive, and
   for a lookup the false positive is the worse one.** Exact-base matching hid
   genuine siblings; bare-prefix matching then let an unrelated shorter
   marker's revision answer. The stable fix was neither loose nor strict but
   RECONSTRUCTIVE -- accept a shorter base only at exactly the value the writer
   would have produced. When a reader must undo a writer's transformation,
   re-derive the transformation rather than pattern-matching its output, and
   pin BOTH directions: this file's markers were all `"E"*n` or unrelated
   literals, so no two stood in a prefix relationship and half the contract was
   untested.

9. **A coarse `surfaces` declaration blocks unrelated work.** The bead declared
   `scripts/` (the retrieval script's name was unknown at planning time), which
   collided with an active P0 voice-bug claim writing spike scripts under the
   same directory. The guard refused the claim, correctly. The fix was to narrow
   the declaration to the exact files -- not to override. Worth preferring
   specific paths at creation time when the file is predictable, and updating
   the declaration as soon as it is known.

## Doc freshness

- `docs/components/pdf-filling.md` BUMPED. It tracks `form_kits.py` and
  enumerates the store's editor write/list surface exhaustively, so three new
  archive methods made that list incomplete -- an additive change still
  falsifies an exhaustive list. Added a Revision archive paragraph (the
  primitives, the marker encoding, why the hook is on revert-to-draft, why
  archives are invisible to both catalogues) and re-stamped the date. My first
  pass through this entry claimed the doc stayed accurate; the freshness gate
  correctly disagreed.
- `docs/standards/confirmation-and-audit.md` describes the marker precedence
  this bead consumes but does not change it (author_version is bead xzw5).

## Beads housekeeping

No orphans. Four stale in_progress beads (52qm.1 grouped-control voice fill;
dft1 client-side resume; ggla DRAFT_ filename; oagt Parts 6/7 invariant) all
belong to OTHER work streams -- the deployment track and the voice epic -- and
were left untouched: transitioning another session's claimed bead from here is
the collision the change-surface guard exists to prevent. This bead's own
surfaces were narrowed at claim time (see Lessons 3).

## Files touched

- `backend/services/form_kits.py` (archive primitives, `encode_marker`)
- `backend/routes/editor_kit_routes.py` (`_archive_published_revision` + the
  revert-to-draft hook)
- `scripts/read_kit_revision.py` (new, operator retrieval)
- `backend/tests/unit/test_kit_revision_archive.py` (new, 19 tests)
- `docs/journal/entries/2026-08-06-bd-w3zw-kit-revision-archive.md` (this entry)
