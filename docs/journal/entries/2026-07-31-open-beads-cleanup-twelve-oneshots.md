---
date: 2026-07-31
bead: polyglot-pdf-v208
title: "Overnight cleanup: thirteen standalone one-shot beads, two of them duplicate pairs"
tags: [maintenance, testing, authoring, i18n, bakeoff, telemetry]
---

## Trigger

Maintainer asked for an unattended overnight pass over open beads: work the
standalone one-shots (no epic parent, no dependencies) -- the bug squashes and
nits left behind by earlier reviews -- and close as many as possible without
blocking on input.

Of 119 ready beads, 99 were standalone non-epics. This pass closed thirteen:
twelve with code/test changes, plus `1wtu`, closed as already-resolved after
investigation (see below).

## What shipped

Six commits, grouped so each is independently reviewable:

1. **Two duplicate pairs, fixed once each.** `v208`/`x2qt` were the same defect
   filed twice, as were `w96o`/`0r53`.
   - `measure_form_session_costs.py --help` crashed with `TypeError: %u format`
     for the **whole parser**, because a help string carried a literal `-21%
     unhappy` and argparse runs `help % params`. An AST scan of every
     `add_argument` help string confirmed it was the only bare percent.
   - `arm_llm_native.py`'s docstring advertised a `GEMINI_API_KEY` auth path
     that no longer exists. Verified against the real chain
     (`resolve_provider` -> `GeminiProvider` -> `_vertex_gemini_client`) rather
     than taking the bead's word for it.

2. **Stale animation comments** (`nosv`). Three comments called speaking's shape
   a "halo"; since the 2026-07-29 swap, speaking drives ray-length breathing and
   *listening* owns the halo. Confirmed against `Sol.tsx` before rewording. The
   surviving "halo" mentions in `Sol.test.tsx` are correct post-swap assertions.

3. **Telemetry README bounds** (`64i9`). The doc claimed the two telemetry
   sources partition at 2026-06-10. Measuring instead of trusting: per-file rows
   start 2026-06-01 (378 rows), the JSONL spans 2026-06-01..2026-06-10, and
   **71 of the JSONL's 74 rows are literal `(session_id, recorded_at)`
   duplicates** of per-file rows. The old text ("a given session appears in at
   most one source") would have led an analyst to skip the dedup and double-count
   nearly the whole JSONL.

4. **Deploy-log noise + part-id collisions** (`qwex`, `n2t3`).
   - `_`-prefixed dirs under `form-kits/` are shared authoring data, not kits, so
     the deploy loops warned about `_translation` on every run. The bead named two
     loops; there were four. Confirmed safe to skip: the glossary is read from the
     local repo path, never the GCS bucket.
   - `derive_sections.build_output` deduped section ids but not **part** ids, so
     two part labels that slug identically collided. Reproduced, mirrored the
     existing section dedup, and added derive+repair composition tests asserting
     that a repair does not break the section references derivation established.
     Note the precise scope: those tests call the two functions in the pipeline's
     order but do **not** invoke `extract_form`, so they do not detect a future
     *reorder* of the pipeline itself -- they guard repair's behavior, not the
     call order.

5. **Once-mock leak** (`kas0`). `usePDFDocument.test.ts` reset with
   `clearAllMocks`, which does not drain queued one-time implementations.
   Switched to `resetAllMocks` -- with a wrinkle the bead did not anticipate:
   that also strips the module-scope default, so the happy path is now
   re-established per test. Without it the remaining tests passed only because
   the hook degrades quietly when `getDocument` returns undefined: passing for
   the wrong reason.

6. **Translation-map enforcement** (`vqy3`) and **the AI Studio gate**
   (`kgmn`). See below.

7. **Booklet slice anchoring** (`r0za`). The W-7 `--trim` artifact anchored on a
   forward cross-reference inside category f's prose instead of the real
   "Exception 2." heading, so its slices overlapped and it silently re-included
   box h and all of Exception 1.

## What the work turned up that the beads did not say

**A static guard found a second instance of the defect it was written for.**
`kgmn` scoped itself to `arm_gemini.py`. Alongside the behavioral test, a static
guard over every `scripts/bakeoff/*.py` rejecting `api_key` client construction
immediately failed on `arm_documentai.py:126` -- the byte-identical escape hatch.
An earlier bead had explicitly excluded that file as "genuinely dual-mode", but
its own docstring says the client it builds is the *gemini* client for the
enhancement call (the DocAI client is separate), so it sits squarely inside the
Vertex-only directive. Folded in rather than filed: same two-line change, and
leaving it would have meant weakening the new guard to accommodate it.

**The corrected slice explains the recorded measurement exactly.** `r0za`'s old
buggy slice measures 6,871 chars ~= **1,717 tokens** -- precisely the figure
recorded in `wsao2_runs.json`. The corrected slice is 996 tokens, 42% smaller.
The code carried a standing warning not to "fix" the anchors without re-running
the measurement, so instead of silently invalidating it, the findings doc now
carries a reproduction note: the recorded results **remain valid as recorded** (a
1,717-token payload really did open a healthy session, so the "ceiling lies
between 1,717 and 3,366 tokens" bound holds), but `--trim` will no longer
reproduce that size.

**One bead was already resolved; one test I wrote was wrong.**
- `1wtu` claimed a stale committed fallback manifest. `frontend/public/form-kits/`
  is **gitignored** and deploy-generated (`pull-form-kits.sh` deliberately
  excludes `index.json` from its rsync, "never a source file"). The maintainer's
  local copy is current and the reported `w7-2` entry is gone. Closed with
  findings, no code change -- removing the fallback would have broken local dev
  to fix a staleness that regeneration already handles.
- In `r0za`'s tests, counting `"Exception 1."` across the whole artifact flagged
  the booklet's own legitimate back-references inside the Exception-1 body. The
  test was wrong, not the code; narrowed to assert which slice a heading *begins*.

## Five pre-existing failures, filed not fixed

The full backend suite showed 5 failures. Rather than assume they were unrelated,
stashing all local work and re-running reproduced them identically on a clean
tree. All five pin expectations against `form-kits/w7/schema.json`, replaced by
the gold schema in `7f09dddb` -- 37 field ids newly report guidance-identity-stale
and the overlay's "2 unclaimed widgets" premise is gone.

Filed as `polyglot-pdf-ld0t` (P1) rather than blanket-refreshed to green: the
lint pin's own failure message warns "if the hash formula moved, check for a mass
false alarm before widening it", so each needs a judgement call. Related:
`polyglot-pdf-aliu` may be the better shape for that pin.

## Sidelined, deliberately

- `hy5k` -- the only remaining work is a live Vertex re-measurement. Real spend
  is a maintainer decision and is gated by the experimentation skill's pre-spend
  estimate; an unattended pass is the wrong place to open a billing commitment.
- `c7bx` -- framed as a small refactor; measured 47 `status.toLowerCase()` branch
  points across the two overlays, with the state doing double duty as both state
  machine and rendered display string, and load-bearing prefix matching
  (`startsWith('connected ')`). Left a scoping comment with a staged plan.

## What the review rounds caught

Three Opus outer-review rounds found twelve findings; all were fixed rather than
argued away. The ones worth remembering:

- **A CI-red I would have shipped.** The new once-mock guard constructed a
  `Promise.reject` it deliberately never consumed, so vitest reported an
  unhandled rejection and exited **non-zero with every test passing**. CI runs
  that suite, so the required check would have failed on every run.
- **A test that pinned nothing.** The first derive+repair test passed with the
  ordering *reversed*, because `repair()` makes zero repairs on all three
  committed kits -- it asserted only invariants an existing test already covered.
  Replaced with a synthetic colliding-option schema that forces real mutation,
  and it asserts the mutation happened so it cannot silently go vacuous again.
- **A silent behavior change inside a "pure delegation."** Routing both bakeoff
  arms through the shared helper swapped the location knob from `VERTEX_LOCATION`
  (the repo's canonical one, 23 sites) to `GOOGLE_CLOUD_LOCATION`, so a
  non-`us-central1` run would have quietly hit the default. Fixing that then
  made an **untouched** backend test depend on ambient shell state -- caught only
  because a reviewer ran it with `VERTEX_LOCATION` exported.
- **Prose claiming more than the tests deliver.** Several docstrings (and one
  line of this journal) said the tests "pin the step-3e-before-repair ordering
  contract." They do not: nothing invokes `extract_form`, so a pipeline reorder
  passes clean. Narrowed the claims to what is actually enforced. Follow-ups filed
  as `polyglot-pdf-kow7` (a real ordering guard) and `polyglot-pdf-cnwz`
  (`DISCLAIMER_TRANSLATIONS` has no `SPOKEN_LANGUAGES` anchor either).

The through-line: every one of these was found by *running* something -- a
mutation, an env var, a reverted fix -- not by reading the diff.

## Doc-freshness note

`closeout_prep` flags `docs/technical_guide.md` as stale against
`deploy-all.sh`. Reviewed: the guide mentions `deploy-all.sh` only as a deploy
entrypoint (line 21) and does not document the kit-iteration loop this change
touched, so nothing there is invalidated -- the flag is mtime-based. The rest of
the stale list is pre-existing and untouched by this branch.
