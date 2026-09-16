---
date: 2026-09-16
bead: polyglot-pdf-jub5f
title: "feat(deploy): E4.4 staging-before-demo gate -- pure predicate, build step, route refusal, both directions proven"
sprint: 22
tags: [testing, doctrine]
---

## Trigger

Epic 4 bead 4.4 of `docs/sprint_22_admin-console_plan.md` ("Staging-before-
demo predicate"). Bead 4.2 had already shipped the pure predicate
(`admin_backend/services/promotion_gate.py::staging_verified`) and the
build-step CLI (`scripts/promotion_gate.py`) as a working placeholder so
4.2's own gate steps had something real to call; bead 4.3 then consumed the
same predicate for `POST /admin/deploys`'s early, friendly 409. 4.4's job
was to close out the exit criteria those two beads left open: a dedicated
test file proving both directions through the real route plus the CLI's
exit codes, the build gate's runtime evaluation checked for BOTH the target
family and the SHA (not just the family), and the doctrine doc recording
where the gate lives and the no-recency decision.

## What shipped

Reading the already-shipped code (`admin_backend/services/promotion_gate.py`,
`scripts/promotion_gate.py`, `admin_backend/routes/deploy_routes.py`,
`cloudbuild.yaml`) confirmed the production behavior bead 4.4 asks for was
already correct and already had its own tests
(`admin_backend/tests/unit/test_promotion_gate.py`,
`admin_backend/tests/unit/test_deploy_routes.py`,
`tests/test_cloudbuild_yaml.py`). So this bead's actual work was closing
three real gaps rather than changing behavior:

1. **`admin_backend/tests/unit/test_demo_promotion_gate.py` (new).**
   Consolidates, in the one file the bead's exit criteria name, the three
   directions: the route's 409 (naming the missing family/sha) and 200
   through a real `TestClient` request; the predicate's case table (wrong
   family, wrong sha, status failure, and the no-recency rollback case) in
   the bead's own words; and `scripts/promotion_gate.py`'s exit codes (0
   verified, 1 refused, 1 fail-closed on a query error), both as an
   in-process function call under a monkeypatched query AND as a real
   subprocess with a stub `google/cloud/firestore.py` module shadowing the
   real one (the bead's own "subprocess test with a stubbed store"
   wording). Every test was mutation-verified by hand: dropping the
   status check, adding a recency rule (picking only the newest staging
   record), short-circuiting the route's gate check, and inverting/removing
   the CLI's branches and its fail-closed guard all turned the matching test
   red, then were reverted.
2. **`tests/test_cloudbuild_yaml.py`.** The existing runtime-evaluation test
   for `staging-verified-gate` (`backend-demo`/`frontend-demo`) asserted only
   that the target-derived `--target-family` reached the stubbed `python`
   interpreter, not that `--sha` did too -- so a build step that dropped
   `--sha` from the invocation would have passed. Added that assertion, and
   added the SAME runtime evaluation (rendering the step's real bash,
   stubbing `python`/`pip`, asserting the invoked args) for
   `admin-service-staging-gate`, which previously had only a static
   substring check that could not tell a live case arm from a broken one.
   Mutation-verified all three: dropping `--sha` from either gate step, and
   breaking `admin-service-staging-gate`'s own `if` guard so it always hits
   the skip arm, each reddened the new assertion.
3. **`docs/doctrine/promotion-tiers.md`.** Added a "The staging-before-demo
   promotion gate" section: where the rule lives (the pure predicate), where
   it is enforced (the build) versus where it is only a courtesy (the
   route's early refusal), why the admin service is deliberately excluded
   from that early route check (its staging-equivalent proof is written
   mid-build, by an earlier step of the SAME build that later reads it -- a
   pre-build route check could never find a row for a brand-new SHA), and
   the no-recency decision recorded as the maintainer-reversible call the
   plan flagged it as.

**Review round (cross-surface, Opus).** GAPS-FOUND (1): the new "staging-
before-demo promotion gate" section stated the gate as current, live
behavior with no hedge, while the sanctioned bash deploy path
(`deploy-demo.sh` -> `deploy-all.sh`'s bare `gcloud builds submit --tag` /
`gcloud run deploy` / `firebase deploy`) never invokes `cloudbuild.yaml` and
so never reaches the gate -- the exact false-safety belief the staging tier
exists to prevent. **Adopted**: opened the section with a hedge naming bd
`polyglot-pdf-oqtm7` (E4.6, blocked by this bead) as the connection point,
matching the hedge the preceding "Deploy is moving into Cloud Build" section
already carries. Two pre-existing/nit findings from the same round were
**deferred** as filed beads rather than fixed here: the fourth stacked
`*Last updated:*` stamp in `config-deployment.md` being invisible to
`check_doc_freshness.py`'s first-match regex (`polyglot-pdf-fjxce`), and
`deploy_routes.py`'s module docstring still listing `admin-service` inside
`GATED_TARGETS` (`polyglot-pdf-cvmig`, reproduces unchanged on `origin/dev`).
No finding was rejected. No production code changed by the fix round --
docs only.

No production code changed. The bead's own text ("the same check on the
admin-service traffic-shift target") reads as if the route should gate
admin-service too, but bead 4.3's own shipped code already deliberately
does the opposite, with its own passing test
(`test_admin_service_is_not_refused_by_the_early_gate`) and a detailed
`deploy/targets.py` docstring explaining why: the admin service has no
separate staging build, so a pre-build route check could never find a
staging row for a new SHA and would refuse every admin-service deploy
forever. Treated 4.3's shipped decision as authoritative (code over an
earlier bead's prose when the two conflict) rather than regressing a
working, tested design -- documented in `promotion-tiers.md` rather than
re-litigated in code.

## Lessons

- A "gains the assertion that X invokes Y with A and B" exit criterion is
  easy to half-satisfy: the pre-existing runtime test already asserted A
  (the family) and looked done, but never checked B (the SHA) at all. When
  an exit criterion names two things a call must carry, write an assertion
  for each one explicitly, not just enough to make the test read as
  covering the sentence.
- Closeout tooling (`closeout_prep.py`) resolves the worktree to audit via
  `git rev-parse --show-toplevel`, which trusts the process's OWN `cwd` --
  and a `run_in_background: true` Bash call in this harness did NOT honor an
  inline `cd "$WT" && ...` the way a foreground call does, silently auditing
  a different worktree entirely (the session's primary working directory)
  with a clean-looking but WRONG result. The fix that actually works under
  backgrounding: `os.chdir()` inside the Python process itself (e.g. via
  `python -c "import os; os.chdir(r'<WT>'); ..."` or `runpy.run_path`), never
  a shell-level `cd` on a backgrounded call.

## Doc freshness

`docs/doctrine/promotion-tiers.md`: added the new section and bumped its
*Last updated:* stamp. `docs/components/config-deployment.md` (its own
`Tracks:` line already names `admin_backend/services/promotion_gate.py`,
`scripts/promotion_gate.py` and `cloudbuild.yaml`): added a pointer stamp
rather than duplicating the doctrine doc's narrative. `closeout_prep.py`'s
doc-freshness audit still flags `config-deployment.md` (and ~20 other
tier-2 docs) STALE against files this bead did not touch (e.g.
`deploy-all.sh`, `backend/deploy-new.sh`, `.firebaserc`, `backend/config.py`)
-- pre-existing staleness, reviewed and left for whichever bead actually
owns those files, per this bead's own declared surfaces.

## Files touched

- `admin_backend/tests/unit/test_demo_promotion_gate.py` -- new, the bead's
  own consolidated exit-criterion test file.
- `tests/test_cloudbuild_yaml.py` -- `--sha` assertion added to the existing
  `backend-demo`/`frontend-demo` runtime test; new runtime evaluation test
  for `admin-service-staging-gate`.
- `docs/doctrine/promotion-tiers.md` -- new "staging-before-demo promotion
  gate" section; stamp bumped to 2026-09-16.
- `docs/components/config-deployment.md` -- pointer stamp added.
