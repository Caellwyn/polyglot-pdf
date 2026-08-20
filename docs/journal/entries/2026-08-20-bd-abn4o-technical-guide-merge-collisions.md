---
date: 2026-08-20
bead: polyglot-pdf-abn4o
title: "technical_guide merge collisions: the stamp narrative and the routes table"
sprint: null
tags: [conventions, testing]
---

## Trigger

The maintainer reported frequent merge conflicts across parallel agent
sessions, concentrated in docs and worsening recently -- suspecting the
tightened docs discipline as the cause. It was, though not the way "more doc
edits" would suggest: the discipline concentrates edits onto the SAME PHYSICAL
LINES of a few shared files, which is the one thing a line-based merge cannot
tolerate.

Measured on origin/dev over 8 weeks, commit counts as a contention proxy:
technical_guide.md 38, standards/ws-protocol.md 34, INDEX.md 26,
components/config-deployment.md 24, components/voice-ai.md 23. The maintainer
then named technical_guide.md as the file conflicting that day, so the hunk
headers of the 12 commits touching it in the week to 2026-08-20 were read
directly:

- stamp paragraph (L1-24): 12 of 12 commits -- every one
- routes table (~L96-116): 7 of 12 commits
- Surface-contract appends (EOF): 4 of 12 commits

(Re-measured at the end of the review loop, because the window kept filling as
work landed: the first count, taken mid-bead, saw 11 commits and read the zones
as 8/8/2. The re-count over the same 08-14..08-21 window strengthens the case
rather than weakening it -- the stamp paragraph was touched by EVERY commit that
touched the file. The zone ordering that drove the scoping decision is unchanged:
stamp first, routes table second, EOF appends last.)

## What shipped

- **The stamp narrative is gone.** It had degenerated from a one-line date
  into a 22-line running changelog that each PR APPENDED prose into ("Same
  day, bd X... Also same day, bd Y..."), stacking four beads' narratives.
  Every PR rewrote and rewrapped it, so any two parallel PRs conflicted with
  certainty. It also violated this repo's own tier-1/2 "CURRENT STATE ONLY --
  history goes in the journal" rule (doc-architecture.md). Its content --
  date, bead, what changed -- is exactly what `git log` and these journal
  entries already record. The durable, current-state sentences it had buried
  (the Surface contracts pointer, the continuous-DTI defaults, the
  deploy-flow scope note) were kept; the three bead ids it cited (7872, 55jg,
  n18q) all survive elsewhere in the file, verified by grep rather than
  assumed.

- **`tests/test_technical_guide_routes_table.py`** -- the SET PIN for the
  routes table, modelled on
  `test_http_route_auth.py::test_every_client_tier_kit_read_is_visibility_gated`.
  Derives the shipped route set from the live FastAPI app and asserts the doc
  documents every one, in both directions (undocumented route; phantom row).

- **The routes table is sorted by (path, method), pinned by a third test.**
  This is the half that addresses COLLISIONS rather than drift. The previous
  order was conventional-but-arbitrary (`lint` -> `status` ->
  `retire-candidates` -> `lock` -> `DELETE {kit_id}` -> `readiness` -> `POST
  kits` -> `extract`), which gives a new row no determined home: two parallel
  PRs pick different insertion points and collide. Sorting gives every row
  exactly one correct position. The convention is stated in the guide above
  the table, so the next author sorts rather than appends.

- **Eight undocumented routes documented.** The new test's first run found the
  table was already nine routes stale (the ninth was covered by an ellipsis
  row): `store-handshake`, `draft-snapshots`, `draft-snapshots/{id}/restore`,
  `repair`, `derive-divisions`, `regenerate-guidance`, `unclaimed-widgets`,
  and `label`. Each row was written from the handler's own docstring and
  decorator -- role tier, write-lock behavior, and the deliberate error-code
  choices (422 vs 500 vs 409) -- not from inference.

## Decisions

**Generating the routes table was rejected; a completeness test plus a stable
sort replaced it.** Generation was the proposal's preferred option and does
remove the conflict class outright, but each row's value is its hand-written
"Surface doc" prose -- which surface owns the route, what the auth gate is, why
a 409 fires -- and a generator would either discard that or need the prose
stored elsewhere, moving the conflict rather than removing it. The pairing that
replaced it covers both failure modes: the completeness test kills DRIFT, and
the (path, method) sort kills COLLISIONS by giving every row exactly one
correct position.

The first version of this change shipped only the test, and the fresh-eyes
review correctly scored that a FAIL against the bead's second exit criterion:
a completeness test catches a missing row but does nothing about two PRs
editing the same region, which is the problem the bead actually measured. The
sort was the cheap fallback the bead named and the first pass skipped without
addressing it. Both halves are now in.

**The Surface-contracts split was deferred** to polyglot-pdf-m2j14 rather than
shipped here, on the bead's own evidence. It addresses the least frequent
collision zone (4 of 12 commits, against 12 of 12 and 7 of 12 for the two zones fixed
here), and the enumeration showed it is a change to REVIEW INFRASTRUCTURE, not
doc layout: it touches the tier lists in three review agents plus the closeout
skill, TIER1_DOCS in check_doc_freshness.py, seven assertions in
test_doc_freshness.py, and -- most consequentially -- the single pointer the
blast-radius reviewer depends on. Bundling that with two cheap, high-value
edits would have made one PR that is half trivial and half consequential.

## Traps found (recorded on the beads)

- **The blast-radius reviewer would lose the map silently.**
  `.claude/agents/cross-surface-reviewer.md:52` reaches Surface contracts only
  through a plain technical_guide.md link whose description enumerates "route
  table, environment split, gotchas" and never mentions the map. After a split
  the agent whose entire job is the blast radius follows that link, finds the
  map gone, and gets no error and no broken anchor to signal it.

- **A "contract N" namespace collision.** validation-delegation.md defines its
  own "Frozen contract 1..6", cited ~30 times across backend/ and docs/. A
  repo-wide `s/contract N/.../` rewrite during the split would corrupt all of
  them. Exactly three prose citations belong to Surface contracts
  (technical_guide.md L157, L425, L485).

- **The freshness script's stated objection to git-derived dates is
  overstated.** Its docstring (:33-38) warns that a commit touching both code
  and doc "still flags as stale... because the comparison is `file_ct >
  doc_ct`". Both sides come from `git log -1 --format=%ct`, so in a single
  commit the timestamps are IDENTICAL and strict `>` is False -- the named
  failure mode does not occur. The case that does bite is doc-first-then-code
  in separate commits. Recorded on polyglot-pdf-9hdt4 so the repo-wide stamp
  removal does not re-derive it.

## The review round (and the lesson in it)

The fresh-eyes pass found three gaps, two of them real bugs in the first
version of this change. Both are worth recording because they are the same
class of mistake in different clothing: **trusting a convenient artifact
instead of the shipped one.**

- **The completeness test had a hole big enough to drive a route through.**
  `_resolve_ellipses` expanded the table's `.../pdf` shorthand against EVERY
  concrete path in the table rather than the shorthand's own row, inventing 21
  paths no row documents (`/api/tts/pdf`,
  `/api/editor/kits/{kit_id}/draft-snapshots/{snapshot_id}/pdf`, ...). A new
  route matching any ghost passed the check silently -- the exact mutation
  class the test's own docstring claimed to guard. My mutation verification had
  used a route shape that happened not to collide with a ghost, so it went
  green for the wrong reason. **A mutation that passes tells you nothing unless
  it is the mutation most likely to happen.** Fixed by resolving shorthand
  per-row; re-verified with the reviewer's ghost-shaped route, which now fails
  the test by name.

- **A new doc row asserted behavior the code does not have.** The
  `store-handshake` row claimed `reason="unwritable"`. The handler
  (`editor_kit_routes.py:993-1007`) returns `mismatch`, `stale`, or
  `not-a-local-store` and never `unwritable`. I had written the row from the
  handler's DOCSTRING (:976), which is stale, rather than its return
  statements -- while writing a change whose entire premise is that docs drift
  from code. The repo's own rule already covers this (verify claims against
  code, not prose); the row now names the three real values.

The pre-existing docstring/comment drift at `editor_kit_routes.py:193` and
`:976` is out of scope here and filed as bd polyglot-pdf-ffnbc -- which also
asks whether the editor client switches on those strings, since an undocumented
`"stale"` and a fictional `"unwritable"` could be a real unhandled branch rather
than just stale prose.

Round 2 confirmed both fixes and found the same class of hole one more time,
in a narrower corner: `_documented_routes` scanned the WHOLE table row, so a
path name-dropped in a row's DESCRIPTION cell ("the `/status` promotion gate",
"no `/api` prefix") counted as a documented route. A future route literally
named `/status` would have passed the completeness check with no row of its
own -- again, a doc claim satisfied by unrelated prose. The parser now reads
only the Path column, which also let two compensating filters come out of the
phantom test. Both `/status` and `/api` are now correctly reported as
undocumented.

Round 3 scored both criteria PASS with no gaps, but flagged a FOURTH instance
of the same shape, still dormant: both parsers hardcoded `cells[2]` as the
Path column, so a literal `|` before that column (the table already uses an
escaped `\|` in one description) would shift every column right and the row
would silently document nothing. No current row triggers it -- a shift needs a
pipe in the Method cell, and all 37 rows hold a bare verb.

**At that point the instance was the wrong thing to fix.** Scar #7's tell had
fired exactly as written: three review findings differing only in location.
So rather than add a fourth filter, the parser now REFUSES TO GUESS. One
shared `_parse_row` locates the columns for both consumers and raises on any
row it cannot parse unambiguously, and a new fourth test pins the property all
four instances violated: every row must parse into locatable columns with a
real path in the Path column, and no two rows may share a sort key. A row that
cannot be parsed now fails loudly instead of quietly contributing nothing.

The generalizable lesson: when a checker infers a claim from a text region,
the region must be exactly the claim's scope -- widening it to "the whole row"
or "the whole table" silently converts nearby prose into evidence. And when
the same finding arrives three times in different locations, stop fixing
instances and go pin the property. Stored as repo scar tissue via
`bd remember` (key `a-checker-that-infers-a-claim-from-text`).

Round 2's third finding was mine to own: exit criterion 2 required a follow-up
bead if the stable-sort branch was taken rather than generation, and I took
that branch without filing it. Filed as bd polyglot-pdf-m1ulw -- deliberately
framed as "measure whether the sort worked, generator only if it did not",
since building it speculatively would discard the reasoning that rejected it.

## The outer review found what four inner rounds could not

The Opus cross-surface pass returned GAPS-FOUND (2), and both live OUTSIDE the
diff -- which is exactly the split between the two review layers. Four
fresh-eyes rounds read this change carefully and could not have found either,
because neither is in a file the diff touches.

**The dangerous one: the change had a path to silently reverting itself.**
`.claude/skills/closeout/SKILL.md` tells every closing agent, unconditionally,
to "bump its `*Last updated:*` line" for each stale doc whose `**Tracks:**`
covers a file the branch changed. `technical_guide.md` tracks
`backend/routes/*.py`. So the NEXT route PR would list this doc as stale, and
the skill's remedy is precisely the stamp this bead deleted -- re-added in good
faith, by an agent following the documented process. The skill now names the
exception and says to fix the prose and stop.

**The second: the doc that DEFINES the convention now contradicted the corpus.**
`docs/doc-architecture.md` opened its stamp section with "Every tier-1/tier-2
doc carries a one-line stamp." A reader following the rule would re-add it.
Now "Nearly every", with the exception, its rationale, and the git-fallback
behavior spelled out.

Both are the same failure mode as the diff's own bug class, one level up: a
rule stated in one place, a corpus changed in another, and nothing connecting
them. The lesson from scar #7 -- enumerate the set before changing any of it --
applies to a convention's STATEMENTS as much as to its instances.

The pass also found the new gate was **method-blind**: `_shipped_routes`
discarded `route.methods`, so a new HTTP method on an already-documented path
would ship undocumented with the suite green. Fixed here rather than deferred
(bd polyglot-pdf-zvjs2, closed) -- both sides are now keyed on
`(path, method)`, and the mutation that proves it is exactly the escape
described: a `DELETE` on `/api/form-kits/{kit_id}/schema` now fails by name
where it previously passed. The table needed no new rows; it was already
method-complete, since each of the three two-method paths already had a row per
method.

## Verification

- All four tests mutation-verified, with each mutation confirmed applied by
  grep before the run and the file restored by hash afterward: an undocumented
  route turns `test_every_shipped_route_is_in_the_guide_routes_table` red
  (naming the route); a NEW METHOD on an already-documented path turns the same
  test red (`DELETE /api/form-kits/{kit_id}/schema` -- the escape that passed
  green under the path-only key); a phantom doc row turns
  `test_guide_routes_table_documents_no_phantom_routes` red; swapping two
  adjacent rows turns `test_guide_routes_table_is_sorted_by_path_then_method`
  red (naming the divergence); an escaped `\|` in a Method cell turns
  `test_every_routes_table_row_parses_unambiguously` red (naming the row and
  saying why).
- The earlier mutations were RE-verified twice: after the shared-parser
  refactor and again after the `(path, method)` key change, since each altered
  the code path all four tests run through. A refactor that quietly broke a
  guard would otherwise read as a clean green.
- `docs/doc-architecture.md` also claimed the freshness checker is "a CI gate
  via tests/test_doc_freshness.py". That needed splitting, not simply denying,
  and the first attempt at it OVER-CORRECTED to "warn-only everywhere" -- which
  the outer review's round 2 caught as flatly wrong for one half. The checker
  has two halves with different enforcement:
    - **Staleness** is warn-only: the script always exits 0 and the suite pins
      that logic against synthetic fixtures, never the real corpus. This is how
      20 tier-2 docs sit stale with a green suite.
    - **The current-state-only convention IS a real CI gate**:
      `test_no_history_chains_in_current_state_docs` calls
      `check_doc_conventions()` over the REAL corpus and raises on any finding.
  The over-correction would have taught the next reader that a `Previously:`
  chain cannot redden a test -- exactly backwards, in the doc whose own rule 3
  that gate enforces. Mutation-verified before rewriting: appending a
  `## Changelog` to a tier-2 doc reddens that test by name.
- The ellipsis fix re-verified against the mutation that DEFEATED the first
  version: a route at `/api/editor/kits/{kit_id}/draft-snapshots/
  {snapshot_id}/pdf` (a path shape the old parser invented as a ghost) now
  fails the completeness test by name. Ghost count went from 21 invented paths
  to 0.
- The stamp removal's real risk -- that dropping the stamp drops the doc out
  of the freshness discipline -- was mutation-verified too: with no stamp,
  `parse_last_updated_ts` returns None and the git fallback supplies the date;
  forcing that fallback to epoch 0 flipped `check_doc` from `ok` to `stale`
  with 23 files flagged. The fallback is load-bearing, not a silent skip.
- `tests/test_doc_freshness.py`: 105 passed. Root suite `tests/`: 1189 passed,
  1 skipped. Backend suite via closeout_prep: 2402 passed, 2 skipped.
- closeout_prep's other two flags were triaged, not ignored: the stale bead
  (`polyglot-pdf-ly00c`) is someone else's in-progress work, and the 20 STALE
  docs are pre-existing -- verified by confirming this branch's diff touches
  none of them. That staleness is recorded as evidence on the epic: 20 of ~24
  tier-2 docs are stale, so the repo is paying the stamp's full merge-conflict
  cost for a freshness signal it is already ignoring at scale.

**A near-miss worth recording:** the first full-suite run reported exit code 0
while running ZERO tests -- pytest had rejected an unrecognized `--timeout=300`
argument. The exit code alone would have read as green. Read the counts, not
the code (this repo has burned that lesson before).
