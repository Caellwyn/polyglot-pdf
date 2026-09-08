---
date: 2026-09-08
bead: polyglot-pdf-6p77c
title: "Editor 'deploy this form' never reached the app -- the bundle, not privacy, is the discriminator"
tags: [hotfix, testing, doctrine]
---

## Trigger

The maintainer could not open the I-90 in the deployed voice app. The W-7 worked;
the I-90 failed with:

```
Error loading form
Unexpected token '<', "<!DOCTYPE "... is not valid JSON
```

They had published the form from the hosted schema editor -- repeatedly, and
re-deployed -- with no effect.

The reported symptom pointed at the kit. It was not the kit.

## What shipped

### The bug: a discriminator that was never the real one

`GET /api/form-kits` advertises each kit's schema/pdf path. It rewrote that path
to the authenticated backend route (`/api/form-kits/{id}/schema|pdf`) for a
PRIVATE kit, and otherwise served the STATIC Hosting path
(`/form-kits/<id>/schema.json`). The stated reason was that the static bundle
excludes private kits.

True, but not the whole condition. The bundle is generated at frontend BUILD time
by `generate-form-manifest.ts`, which indexes the local `form-kits/` directory --
so it excludes **everything not committed to git**, public kits included. The
hosted editor publishes into the GCS bucket, which is the canonical store. A kit
can therefore be `complete`, public, and perfectly serveable while being absent
from the bundle. Its static path then falls through `firebase.json`'s SPA
catch-all, returns `index.html` with **HTTP 200**, and the client's `JSON.parse`
dies on `<!DOCTYPE`.

Privacy was never the discriminator. **Presence in the static bundle is** -- and
in GCS mode that is not knowable from the route. So the gate became
`is_private or isinstance(store, GCSFormKitStore)`: in GCS mode every kit routes
through `/api/`. Local mode keeps static paths, where the store root *is* the git
tree and they resolve by construction. Two new tests, mutation-verified.

This is the whole runtime fix. One condition.

### The wrong turn, and what corrected it

The first several commits on this branch solved a different problem: they
COMMITTED the kit to git so the frontend build would bake it in. That fought the
architecture instead of using it, and it took a maintainer correction to see it --
"the kits online are the canonical collection, not anything in git or in local
folders... the gitignored folder is meant to be a place where I can rapidly work
and update locally before deploying to the remote, not an official store."

That correction is now scar tissue (CLAUDE.md #10) rather than tribal knowledge,
because nothing in the repo said it and the code's own comment pointed the wrong
way.

### The corollary the maintainer drew, which was the larger half

> "why do we have tests specific to specific forms when those forms are going to
> be shifting all the time? ... There are likely going to be hundreds of form
> kits at some point, if not thousands. We need to be creating the foundations
> for that."

Measured on this ONE kit swap:

| | count |
|---|---|
| test files hardcoding a specific field id | 52 |
| total hardcoded field-id references | 530 |
| ...that READ a real shipped kit | **22** -- all 22 broke |
| ...that use SYNTHETIC fixtures | 16 -- zero broke |

The coupling costs, not the specificity: `test_dti.py` and
`test_confirm_field_tool.py` both use `p1_line1_aliennumber`, an id in no shipped
kit any more, and pass -- they never open a kit.

So `form-kits/i-90/` is untracked, `.gitignore` states the principle rather than
naming one kit, and four test files DISCOVER their kit set from
`git ls-files form-kits/` instead of naming forms. `w7`/`f1040` stay tracked as a
documented exception (f1040 is not in the bucket -- untracking it would delete
the only copy).

**The decoupling dissolved 20 test failures** that had been scoped as "blocked on
re-authoring the g1b persona" (bd `polyglot-pdf-zc31q`). They were a symptom of
the coupling, not of anything broken. Re-authoring that 132-key persona against
the new schema would have rebuilt the identical trap one kit later; `zc31q` is now
P4 and reframed as "is this measurement wanted, and should it use a synthetic
kit?" rather than a blocker.

### Review

Fresh-eyes: 2 rounds. Round 1 scored all three exit criteria PASS with
independent mutation verification, and found 2 gaps (both fixed). Round 2
re-scored PASS and found 3 more (all fixed, below).

Outer Opus cross-surface: **6 passes**, each looped to its fixes. What they caught
is the substance of this entry's Lessons.

Triage: adopted 11 findings inline; filed 14 beads for pre-existing or
out-of-scope work (`2r1ku`, `iuhkk`, `a4n7h`, `12whb`, `1tfhf`, `lu3ec`, `bg8s8`,
`efesu`, `jvfxc`, `zu7f2`, `e2ekn`, `q6fep`, plus `9vbvt` and `1mgkq` filed
during the work); rejected none as incorrect.

Round-2 findings, all fixed inline:
- `discovered_kits()`'s non-vacuity guard had two `return []` paths that bypassed
  it -- including the "git unavailable" case its own comment named. Every exit now
  asserts; both paths mutation-verified.
- The new far-pair plant in `scenario_events.py` spoke an 8-digit A-Number where
  the corpus canon is 9 (`123456789`), which would have scored a live correction
  against a value contradicting the persona's own answer.
- A citation pointed at `a4z1w` (the eval benchmark manifest) for suffix-fallback
  coverage; repointed to `2r1ku`, which actually tracks the CI-dead kit tests.

Also found at closeout, independent of the reviewers: **a bead id that did not
exist**. I filed the test-coupling bead mid-session, misread the truncated create
output, and propagated `polyglot-pdf-o9zwe` into CLAUDE.md, `.gitignore` and 9
code comments. The real id is `polyglot-pdf-1mgkq`. Caught when `bd show` returned
"no issue found"; fixed by a `git ls-files` sweep rather than recall, which is
what caught a bare `o9zwe` with no prefix that a full-id replace would have missed.

### Not fixed here, deliberately

- `polyglot-pdf-9vbvt`: `firebase.json` has no `/form-kits/**` rewrite, so a
  missing kit asset returns 200 HTML instead of 404. **This is what turned a
  simple "kit not deployed" into an inscrutable parse error**, and it will mislead
  again.
- `polyglot-pdf-38p0y`: `mail_unit_number` is `read_only: true` while its
  identical twin `phys_unit_number` is not, and `isFieldReadOnly` returns `true`
  unconditionally with an in-code comment conceding the unlock check is
  unimplemented. A user who picks a mailing unit type is asked for the number and
  the voice model refuses to write it. The schema half is kit field data (must go
  through the editor); the frontend half is an unimplemented feature.
- `polyglot-pdf-6p77c`'s own caching consequence: routing public kits through
  `/api/` moves their bytes off Firebase's cached CDN onto Cloud Run with
  `Cache-Control: no-store`. Correct for the bug -- a cached 200 of the WRONG
  bytes is worse -- but a real latency/egress change worth measuring on staging.

## Lessons

**A comment can be true and still be the wrong condition.** The `is_private` gate
had a correct-sounding justification ("the bundle excludes private kits") that was
a strict subset of the real rule ("the bundle excludes everything uncommitted").
Six review passes went by before anyone questioned the *condition* rather than the
*code*. When a guard's stated reason is true, ask whether it is the WHOLE reason.

**Verify under the conditions CI will actually see, not the ones your machine
has.** This bit twice in one branch, the same way both times: a test's witnesses
lived in an untracked scratch kit, so it looked alive locally and skipped in CI --
and I reported it as fixed on that evidence. The second time I had explicitly been
warned by the previous round. The check that settles it is
`git clone --depth 1 --branch <branch> file://<worktree>` and run there; anything
else is an assertion about one developer's disk. Stored as
`bd remember verify-in-a-clean-clone-not-your-worktree`.

**A negative assertion is not a pin when two branches share the negation.**
Rewriting a guard, I kept `assert "read ALL" not in text` and dropped the positive
half. Two consecutive branches in `ai_context` both omit that string, so a
62-option dropdown could silently re-route between them with the test green. The
reviewer demonstrated it. Writing the fix then taught me something better: all
three witnesses hit the exemption branch *including* the 62-option one, because the
exemption is checked before the threshold -- so pinning the single positive string
asserts that PRECEDENCE and is stronger than the per-branch conditional I first
tried.

**Aspirational prose in a tier-1 doc is a trap.** Scar #10 as first written said a
test "must never" assert a named field id -- while the same diff shipped three that
do. An always-loaded absolute rule the tree violates sends the next session either
to "fix" a tracked exception or to trust a rule nothing enforces. It now binds NEW
tests and names the live violations as debt owned by `1mgkq`.

**Run every testpath.** `pytest.ini` declares two (`backend/tests` and `tests`). I
ran one for most of this branch and called it green; the other had 28 failures
waiting. A filtered run is not a suite.

## Doc freshness

- `docs/components/pdf-view.md` -- **bumped**. It stated the per-option
  `pdf_position` kit list in three places and my earlier edits updated only some,
  so a current-state doc contradicted itself. Reconciled on the measured truth
  (f1040 9 fields, w7 6) and the retired-gap paragraph no longer implies the
  canonical I-90 lives in the repo.
- `docs/components/pdf-filling.md` -- **bumped**. The suffix-fallback claim said
  "no SHIPPED kit" and "unexercised by COMMITTED data"; under bucket-canonical
  those are no longer the same set, and the 79/79 figure cited is the bucket's
  I-90, not a committed one.
- `docs/technical_guide.md` -- **prose updated, no stamp added** (it deliberately
  carries none). Its Surface-contracts map still described the rewrite as
  private-only, which this change makes wrong; rewritten as "The API-path
  rewrite".
- Two `*Last updated:*` chains I had introduced were **pruned**. Their phrasing
  ("earlier note follows") slipped past `check_doc_freshness.py`'s
  `Previously|Prior|Earlier` pattern, so the gate reported clean while a changelog
  re-grew.
- `docs/components/jit-schema.md` -- **reviewed, left**. It tracks
  `ai_context.py`, which this branch touched, but only in comments; nothing it
  claims is affected.
- `auth.md`, `context-compression.md`, `schema-forms.md`, `tool-call-flow.md`,
  `voice-ai.md`, `websocket-routing.md` -- **reviewed, left**. Flagged stale by the
  checker, but each tracks files this branch never touched; they were stale before
  this work.

Two stale `in_progress` beads (`0dsv4`, `ub7om`) are other sessions' in-flight
work, untouched by this branch and left alone.

## Files touched

- `backend/routes/form_kit_routes.py` -- the fix: the GCS-mode path rewrite.
- `backend/tests/unit/test_form_kit_routes.py` -- the two mirror tests
  (GCS routes through `/api/`, local keeps static), mutation-verified.
- `backend/tests/test_form_models_v2.py` -- `discovered_kits()` (git-tracked
  discovery + a non-vacuity guard on every exit).
- `backend/tests/unit/test_dti_si_voice_rules.py` -- `_shipped_fields()` /
  `_short_two_option_fields()` discovery; the long-select guard now reads a frozen
  fixture and pins the exemption BRANCH.
- `backend/tests/unit/fixtures/long_selects_frozen.json`,
  `i90_p7_checkbox7_retired.json` -- frozen real-data pins.
- `backend/tests/unit/test_translation_lint.py`, `test_date_format_resolution.py`,
  `test_ai_context.py`, `test_field_validation_responses.py`,
  `test_kit_line_binding.py`, `test_schema_lint.py`, `test_resume_form_route.py`,
  and the `test_pdf_fill_*` set -- discovery, synthetic fields, or honest
  CI-unverifiable markers.
- `tests/` (root testpath) -- `test_extract_form_backfill.py`,
  `test_extract_form_sections.py`, `test_overlay_field_guesses.py`,
  `test_roundtrip_fill.py`, `test_stress_harness_units.py`,
  `test_check_line_binding.py`; `test_i90_migrated_baseline.py` deleted (it pinned
  a migration whose input no longer exists).
- `scripts/spikes/full_form_script.py`, `measure_form_session_costs.py`,
  `scenario_events.py` -- 51 id renames derived from PDF widget leaves, the
  option-value vocabulary, and the redesigned far-pair plant.
- `CLAUDE.md` (scar #10), `.gitignore` (the principle), `docs/components/pdf-view.md`,
  `pdf-filling.md`, `docs/technical_guide.md`, `.claude/skills/voice-harness/SKILL.md`.
