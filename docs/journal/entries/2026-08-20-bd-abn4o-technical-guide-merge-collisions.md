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
headers of the 11 commits touching it in the week to 2026-08-20 were read
directly:

- stamp paragraph (L1-24): 8 of 11 commits
- routes table (~L96-116): 8 of 11 commits
- Surface-contract appends (EOF): 2 of 11 commits

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

- **Eight undocumented routes documented.** The new test's first run found the
  table was already nine routes stale (the ninth was covered by an ellipsis
  row): `store-handshake`, `draft-snapshots`, `draft-snapshots/{id}/restore`,
  `repair`, `derive-divisions`, `regenerate-guidance`, `unclaimed-widgets`,
  and `label`. Each row was written from the handler's own docstring and
  decorator -- role tier, write-lock behavior, and the deliberate error-code
  choices (422 vs 500 vs 409) -- not from inference.

## Decisions

**Generating the routes table was rejected.** It was the proposal's preferred
option, and it does remove the conflict class outright. But each row's value
is its hand-written "Surface doc" prose -- which surface owns the route, what
the auth gate is, why a 409 fires -- and a generator would either discard that
or need the prose stored somewhere else, moving the conflict rather than
removing it. A completeness TEST keeps the prose, kills the drift, and turns a
missing row into a red test that names itself. The table stays hand-written;
the set is pinned.

**The Surface-contracts split was deferred** to polyglot-pdf-m2j14 rather than
shipped here, on the bead's own evidence. It addresses the least frequent
collision zone (2 of 11 commits, against 8 of 11 each for the two zones fixed
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

## Verification

- Both new tests mutation-verified in BOTH directions, with the mutation
  confirmed applied by grep before each run and the file restored by hash
  afterward: adding an undocumented route to editor_kit_routes.py turned
  `test_every_shipped_route_is_in_the_guide_routes_table` red (naming the
  route); adding a phantom doc row turned
  `test_guide_routes_table_documents_no_phantom_routes` red.
- The stamp removal's real risk -- that dropping the stamp drops the doc out
  of the freshness discipline -- was mutation-verified too: with no stamp,
  `parse_last_updated_ts` returns None and the git fallback supplies the date;
  forcing that fallback to epoch 0 flipped `check_doc` from `ok` to `stale`
  with 23 files flagged. The fallback is load-bearing, not a silent skip.
- `tests/test_doc_freshness.py`: 105 passed.

**A near-miss worth recording:** the first full-suite run reported exit code 0
while running ZERO tests -- pytest had rejected an unrecognized `--timeout=300`
argument. The exit code alone would have read as green. Read the counts, not
the code (this repo has burned that lesson before).
