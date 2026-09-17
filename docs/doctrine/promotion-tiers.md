# Promotion-tiers doctrine: worktree -> local -> dev -> staging -> demo

*Last updated: 2026-09-17 (bd polyglot-pdf-wobtv: the preflight no longer refuses on untracked files -- a Cloud Build trigger run fetches only the named commit from GitHub, so an untracked file can never reach it; untracked paths are now a `[NOTE]`, not a refusal. The three tracked `.firebase/hosting.*.cache` files that firebase's own CLI regenerates on every deploy are untracked and `.firebase/` is now gitignored, since a TRACKED regenerated file dirties the tree the other way regardless of the untracked-file fix. A fresh detached worktree at `origin/dev` (with a `node_modules` junction) is recorded below as the valid workaround for a dirty main checkout.) (bd polyglot-pdf-oqtm7 outer cross-surface review round 3: form kits are no longer selected implicitly by ANY wrapper -- a bare or `--all` run of either channel script skipped `firestore-rules` and the frontend when the unbuildable `form-kits` target failed ahead of them; plus the Cloud Build SA's new `datastore.indexAdmin` grant and the re-run it needs.) (bd polyglot-pdf-p4ale, E4.5: the Cloud Build pipeline's own identity, `polyglot-cloudbuild-sa`, is now provisioned by `scripts/setup-cloud-build.sh` -- role list, resource-scoped actAs on both runtime SAs, and the Pub/Sub service agent's OIDC-minting role, all pinned. `admin-backend-sa` gains the mirror-image actAs grant.) (bd polyglot-pdf-1s3ko: the two wrappers now REFUSE a dirty or unpushed tree before anything else runs, and the declarative half of the Cloud Build pipeline exists -- a root `cloudbuild.yaml` with a per-SHA `verify` gate every deploy target reads, plus `deploy/channels/*.env` as the one config source bash and the build share.) (bd polyglot-pdf-jecrl: firm-billing isolation between staging and the demo no longer rests on staging using its own mock firm -- the mint route refuses a live (or kindless) firm unless the raw `LINK_CHANNEL` is exactly `demo`, and a credit is reserved before any token is signed.) (bd polyglot-pdf-2cwja: added the admin-tier row -- the admin service and console's OWN tagged-revision + candidate-site staging, distinct from the public app's staging/demo split above. No code changed in this bead.) (bd polyglot-pdf-t7drr: recorded the shared-surface decisions for LINK_TOKEN_SECRET and the form-kit editing lock -- both shared on purpose. Earlier the same day, bd polyglot-pdf-3q9qn: client links are isolated per channel -- every token names the channel that may open it and each channel keeps its own redemption ledger, so a staging link no longer opens or burns on the demo.) (bd polyglot-pdf-jub5f, E4.4: the staging-before-demo promotion gate is now finished end to end -- the pure predicate, the build-step enforcement, and the route's early refusal are all documented in a new section below, with the no-recency decision recorded as the maintainer-reversible call the plan flagged it as.) (bd polyglot-pdf-oqtm7, E4.6: deploy is no longer local and manual -- every deploy-*.sh is a thin wrapper that runs Cloud Build triggers at a pushed commit, the inline stages are deleted, and the promotion gate's "nothing deploys through this yet" caveat is retired. The per-instance deploy ask is unchanged.)*

How code promotes from a working branch to the running demo. **This project has
NO production environment** -- `deploy-production.sh` targets a DEAD, unreachable
project and now refuses to run (bd `polyglot-pdf-je6iy`). The **demo** is the
live, outward-facing target; **staging** sits in front of it.

## The tiers

```
worktree (feature branch)        one bead's work; where the agent commits
        |  PR (reviewed: fresh-eyes inner + one outer pass -- Opus for source,
        |      Haiku docs-reviewer for docs-only, none for trivial; looped to clean)
        v
dev                              integration branch + PR base; auto-merge if routine/low-risk & clean, else maintainer merges
        |  deploy-staging.sh (front + backend; gated -- see below)
        v
staging remote                   polyglot-app-staging.web.app -- DISPOSABLE.
                                 Break it freely; nobody is watching it.
        |  deploy-demo.sh, only after staging is verified (gated -- see below)
        v
demo remote server               polyglot-demo-aa709.web.app -- the PROTECTED
                                 target shown to investors and pilot firms.
                                 NO prod beyond this.
```

## Why staging exists

Some bugs appear only once deployed: the Cloud Run WebSocket timeout, Vertex
model-id resolution, the IAM envelope (see CLAUDE.md scar #7 -- a mock cannot
tell you the real dependency is forbidden), the Hosting `/api/**` rewrite, and
the per-mode Vite build. Local testing cannot surface any of them. Before
staging, the only way to find them was to deploy to the demo -- the same URL
shown to investors. Staging is a second copy of the deployed surface so a broken
deploy can no longer take the demo down.

## What is separate, and what is NOT

Staging and demo share ONE GCP/Firebase project (`polyglot-demo-aa709`). This was
a deliberate cost/isolation tradeoff (maintainer, 2026-08-31): a second project
would need its own IAM bootstrap, Firebase Auth user pool, and enrolment run.

| | staging | demo |
|---|---|---|
| Cloud Run service | `polyglot-backend-staging` | `polyglot-backend` |
| Hosting site | `polyglot-app-staging` | `polyglot-demo-aa709` |
| `/api/**` rewrite | -> staging service | -> demo service |
| GCP/Firebase project | **shared** | **shared** |
| form-kits GCS bucket | **shared** | **shared** |
| Firestore | **shared** | **shared** |
| Firebase Auth users | **shared** | **shared** |

**Staging protects against broken CODE reaching the demo. It does NOT protect
against bad DATA.** Concretely, items 1-4 below cross the boundary; items 5 and
6 are listed because they were once open questions and are now settled -- 5
(client links) is CLOSED and records what is still shared with it, and 6 (the
kit editing lock) is deliberately shared because sharing is the correct design:

1. A kit marked `status:complete` deploys to the one shared bucket and appears
   in the **demo's** form list. NEITHER wrapper deploys form kits implicitly --
   not on a bare run and not under `--all`, on either channel. Only an explicit
   `--form-kits` selects the target. (Kits are bucket-canonical and never
   tracked in git, while the `form-kits` build target reads the kit tree from
   the CHECKOUT, so that target cannot currently succeed at all -- where it
   should read kits from is bd `polyglot-pdf-wm7ga`. Publish a kit through the
   hosted schema editor meanwhile.)
2. Firestore writes (`confirmation_events`, `users/{uid}`, `firms`,
   `authorized_emails`) land in the one shared database.
3. `firestore.rules` are PROJECT-wide, not per-site. `deploy-staging.sh`
   deliberately does **not** deploy them; rules ship with `deploy-demo.sh`.
4. A user enrolled for staging can also sign into the demo.
5. **CLIENT LINKS are isolated per channel** (bd `polyglot-pdf-3q9qn`), which
   is the one boundary on this list that is CLOSED. Every token carries an
   `aud` claim naming the channel that may open it, so a staging-minted link is
   refused on the demo and vice versa, and each channel keeps its own
   redemption ledger (`link_redemptions` for the demo,
   `link_redemptions_<channel>` elsewhere) so a staging test cannot burn a demo
   link's single use. `LINK_CHANNEL` is what sets this, and both deploy scripts
   set it explicitly.

   **`LINK_TOKEN_SECRET` is deliberately the SAME on both channels.** Both
   channels bind the identical Secret Manager secret -- it is declared in the
   `[SET_SECRETS]` section of `deploy/channels/staging.env` and
   `deploy/channels/demo.env`, and reaches `gcloud run deploy` as
   `--set-secrets` via the build's `read_channel_section` call. That sameness
   is the intended choice, not an oversight: the signing key is not what
   separates the channels -- the `aud` claim is, and it is checked on every
   redemption regardless of who signed the token. Giving each channel its own key would add nothing (a cross-channel
   link is already refused) while creating a real failure mode, since rotating
   one key silently invalidates links minted by the other. A shared key with a
   per-channel audience is the smaller surface.

   **What is still shared: the FIRM's money, and firm-billing isolation is now
   ENFORCED IN CODE** (bd `polyglot-pdf-jecrl`). A firm carries one
   `balance_credits` and one ledger, not one per channel, and `record_mint`'s
   monthly counter `firms/{id}/link_usage/{YYYY-MM}` is likewise firm-scoped.
   What stops a staging mint from spending a paying firm's money is the mint
   route's gate: a firm whose `kind` is `live` -- or which has no `kind` at all
   -- can only be minted against when the process's **raw `LINK_CHANNEL` env var
   is exactly `demo`**. Staging sets `LINK_CHANNEL=staging`, so it refuses with
   a `403` before any credit is reserved.

   The gate deliberately reads the raw env var rather than
   `link_tokens.link_channel()`, whose default is `demo`: an UNSET channel (a
   laptop, a one-off container, a misconfigured revision) must not look like the
   demo. So an unset channel still mints `aud=demo` tokens for **mock** firms --
   today's behaviour, kept on purpose -- while refusing live ones.

   Create staging's firm with `scripts/bootstrap_firm.py --kind mock` and stamp
   the dev account with it. That is now about being able to mint AT ALL on
   staging, not about damage control: signing into staging with a real firm's
   `firm_id` no longer bills anyone, it simply fails.

6. **The form-kit EDITING LOCK is shared, and that is correct as designed**
   (bd `polyglot-pdf-t7drr`). The lock lives in each kit's `metadata.json`
   inside the shared GCS bucket (`editing_lock`,
   `backend/routes/editor_kit_routes.py`), so it is content in a shared bucket
   rather than a per-service lock: the demo backend and the staging backend
   contend for the same one. That is SAFE, not a defect -- the lock is
   uid-scoped and preemption IS the stale-lock release, so two backends taking
   and releasing it behaves exactly as two editors on one backend already do.
   Deliberately left shared: making it per-channel would let the same person
   hold two locks on one kit and edit it from both, which is worse than the
   contention it would remove. Relevant because `deploy-staging.sh`'s
   `CORS_EXTRA_ORIGINS` explicitly contemplates pointing the hosted editor at
   the staging backend for testing.

Treat kit publishing, rules changes, Firestore writes and client-link minting
as production actions regardless of which channel you ran them from.

## One-time staging setup

Before the first staging deploy (the `.firebaserc` target mapping already ships
in the repo; only the site itself must be created):

```bash
firebase hosting:sites:create polyglot-app-staging --project polyglot-demo-aa709
firebase target:apply hosting app-staging polyglot-app-staging --project polyglot-demo-aa709
```

Then add `polyglot-app-staging.web.app` to **Firebase console -> Authentication
-> Settings -> Authorized domains**. Firebase Auth refuses sign-in from an
unlisted domain *with the whole config present and valid*, so no build check can
catch it -- the failure appears only at a human's first sign-in attempt.

### Public ingress for a NEW Cloud Run service

`--allow-unauthenticated` REQUESTS the `allUsers` invoker binding, but that
request can be **refused while the deploy still succeeds and exits 0** -- the
domain-restricted-sharing org policy
(`constraints/iam.allowedPolicyMemberDomains`) rejects `allUsers`. The service is
then created with no invoker binding and 403s every request at Cloud Run's own
gate, *before any application code runs*. An EXISTING service never shows this:
its binding predates the policy and is not retroactively stripped.

The build's reachability gate (`scripts/verify_service_reachable.py`, run as
`cloudbuild.yaml`'s `backend-reachability-gate` step) **fails the build** rather
than reporting success in that case (bd `polyglot-pdf-pidtg`). If it fires:

```bash
gcloud run services add-iam-policy-binding <service> --region us-central1 --project polyglot-demo-aa709 --member=allUsers --role=roles/run.invoker
```

If that is itself refused, the org policy must be relaxed for the project first.
DRS is currently **disabled** for `polyglot-demo-aa709` (maintainer, 2026-09-01),
so this should now succeed; the gate remains because the policy can be
re-enabled, and because it catches any other cause of a missing binding.

- **Feature branches** always branch off freshly-pulled `dev`. A bead never spans
  PRs (one bead = one branch = one PR); a PR may bundle several small whole beads
  and closes at least one. See [`workflow.md`](workflow.md#bead-lifecycle).
- **`dev`** is the integration branch and the PR base. A PR -> `dev` merge is
  autonomous for a routine low-risk PR that reviewed CLEAN, else the maintainer's
  `gh pr merge` (see "The merge gate"). The agent MAY autonomously
  **sync the local root checkout to `dev`** (pull / fast-forward to `origin/dev`)
  -- that is not a merge.
- **The demo remote** is the live target. Promotion to it is `deploy-demo.sh`,
  gated as below. There is no `main`/prod tier.

## The merge gate

The repo's GitHub ruleset sets **allow_auto_merge=false**, so a PR cannot merge
*itself* on green -- someone must run the merge. Who runs it depends on the
**auto-merge rule** (autonomy increase 2026-07-04; CLAUDE.md "Auto-merge vs.
maintainer merge"): a routine, low-risk PR that an **adversarial** reviewer cleared
CLEAN with green checks is **merged autonomously** (`gh pr merge`) at the end of the
review flow; a **consequence-bearing** PR (affects operational cost / user-facing
features / downstream disruption / substantial multi-surface rework / an approved
plan) is instead **pinged to the maintainer**, who clicks merge. The consequence
line is the same as the step-2 escalation line; when unsure, ping. Full flow:
[`review-flow.md`](review-flow.md).

## The demo-deploy gate (autonomy increase 2026-06-10)

This gate governs the PROTECTED channel. The staging gate follows it.

`deploy-demo.sh` runs the demo family's Cloud Build targets -- backend, form
kits, Firestore rules and frontend -- against `polyglot-demo-aa709`. The agent is authorized to
RUN it -- it is no longer on the NEVER list -- but only with ALL THREE guardrails,
in order:

1. **Local test FIRST.** Run the local stack (`scripts/dev-local.ps1`, via the
   `/run-local` skill: backend uvicorn :8000 + frontend vite :5173) and actually
   EXERCISE the specific change working there. Behavioral verification, not just
   "the server starts." If the change isn't demonstrably working locally, it is
   not a deploy candidate.
2. **Explicit per-instance permission.** Ping the maintainer and get a "yes"
   BEFORE each `deploy-demo.sh` run. This is per-deploy, every time -- NOT a
   standing pre-authorization. The agent may run the deploy; running it without
   that specific yes is the violation.
3. **Post-deploy test-drive.** After the deploy completes, test-drive the LIVE
   demo to confirm the change actually works on the remote. The deploy is not
   "done" until the running demo is verified; a failed test-drive is surfaced to
   the maintainer immediately.

**Step 1 is now satisfied by STAGING, not only by the local stack.** The demo
deploy's precondition is that the change was verified on the *deployed* surface:
run `deploy-staging.sh`, test-drive `polyglot-app-staging.web.app`, and only then
ask for the demo deploy. Local-only verification is no longer sufficient for a
change that can plausibly behave differently once deployed -- that is the entire
class of bug staging exists to catch.

## The staging-deploy gate

`deploy-staging.sh` runs the staging family's Cloud Build targets (and
`verify` first, when the commit has no `build_checks` record yet) against the
staging site/service inside the same project. It is **gated the same way as the
demo deploy** (local test -> explicit per-instance permission -> post-deploy
test-drive). Only the engine changed in bd `polyglot-pdf-oqtm7`; the
per-instance ask did not.

> **Open question for the maintainer, deliberately NOT decided here.** Staging is
> disposable and nobody is watching it, so a per-instance ping before each
> staging deploy may be more friction than it is worth -- arguably staging should
> be standing-authorized like the local stack, leaving the per-instance ask for
> the demo only. That is an autonomy-boundary change (a step-2 call), so it stays
> gated until the maintainer says otherwise. It is NOT a licence for the agent to
> widen it unilaterally.

Two things are gated MORE tightly than the channel itself, because they cross the
staging/demo boundary (see "What is separate, and what is NOT"):

- **`--form-kits`, on either wrapper,** publishes to the SHARED bucket and
  changes the DEMO's form list. Treat it as a demo action whichever channel you
  ran it from. It is never implied by a bare run or by `--all`; you have to type
  it. (And today it FAILS -- see bd `polyglot-pdf-wm7ga` above.)
- **Firestore rules and composite indexes** are project-wide;
  `deploy-staging.sh` never runs the `firestore-rules` target. A rules change
  ships deliberately via `deploy-demo.sh`.

`deploy-production.sh` targets a DEAD, unreachable project (`polyglot-forms-919f2`,
bd `polyglot-pdf-je6iy`) and now **refuses to run**, printing a pointer to the two
live channels. Reviving a real prod channel is a maintainer decision requiring a
reachable project, a full `scripts/setup-gcp-project.sh` bootstrap, real
`VITE_FIREBASE_*` values in `.env.production`, and its own Auth user set.

## Deploy preflight: dirty TRACKED state or an unpushed commit is refused

Since bd `polyglot-pdf-1s3ko`, EVERY `deploy-*.sh` wrapper sources
`scripts/deploy_preflight.sh` and refuses BEFORE anything else runs when:

- **a tracked path is modified or staged** -- `git status --porcelain
  --untracked-files=no` is non-empty; or
- **no remote branch contains `HEAD`** -- the commit exists only in this
  checkout.

Both protect the same claim. A Cloud Build build runs from a COMMIT, and
`build_checks/{sha}` records that that commit's suites passed. Deploying from a
tree with uncommitted changes to tracked files would ship a commit the
operator never looked at while believing they shipped what is on their screen
-- the record would not be wrong about the commit, it would simply be about a
different tree than the one they meant. And a SHA that exists only on one
laptop cannot be fetched by the build at all, nor re-built later by the admin
service, which triggers builds by SHA against the connected repository.

The unpushed check asks which REMOTE branches contain the commit, not whether
it is an ancestor of `dev`: a commit on a pushed feature branch is perfectly
deployable, and that is the normal shape of a staging deploy. A refusal that
names a branch you know you pushed means your remote refs are stale -- run
`git fetch origin` and retry.

**Untracked files are noted, not refused** (bd `polyglot-pdf-wobtv`). Deploy
runs `gcloud builds triggers run --sha=<sha>`, which fetches ONLY the named
commit from the connected GitHub repository -- an untracked file can never
reach that build, so it cannot cause the tree/commit mismatch this guard
exists to catch. The preflight still prints every untracked path as a `[NOTE]`
so the operator sees what is lying around uncommitted, but it does not block
the deploy over it. This matters in practice: this repo's checkouts are
essentially never free of untracked scratch (`Claude outputs/`, `*.bak.py`,
`prep-*.txt` left by other sessions), and refusing over those made the guard
refuse every real deploy attempt. A **tracked** file that firebase's own CLI
regenerates on every run hits the same problem from the other side --
`.firebase/hosting.<target>.cache` was tracked until bd `polyglot-pdf-wobtv`
untracked it and added `.firebase/` to `.gitignore`; a tracked, regenerated
cache file dirties the tree on every Hosting deploy no matter how the
untracked case is handled, so both halves needed fixing together.

This is a mechanical guard, not a new gate: it does not replace the
per-instance permission ask below, it only removes a class of deploy that was
never valid.

**Deploying from a fresh detached worktree is a valid workaround for a dirty
main checkout.** When the main checkout accumulates uncommitted changes that
are not yours to commit or discard, `git worktree add` a throwaway checkout at
`origin/dev` (or the commit you intend to deploy) instead of touching the main
checkout's tree. The frontend build needs `node_modules`; a junction
(`mklink /J`) into the main checkout's copy avoids a full reinstall. This is
what an orchestrator did around bd `polyglot-pdf-1s3ko`'s early days before
this preflight existed to name the problem cleanly.

## Deploy runs on Cloud Build, from a pushed commit

**There is no local deploy any more** (bd `polyglot-pdf-oqtm7`, E4.6). Every
deploy is a Cloud Build build of `cloudbuild.yaml` at an explicit commit,
selected by the `_TARGET` substitution and started through a manual trigger
named `polyglot-<target>`. The `deploy-*.sh` scripts and the admin console are
two ways to press the same button: one engine, so the human path and the
console path cannot drift.

**Why that matters more than tidiness: the gates live in the BUILD.** The
per-SHA `verify` record, the Cloud Run reachability check, the kits-manifest
validation and the staging-before-demo promotion gate are all build steps, so a
bash-started build is gated exactly like a console-started one. Before this,
each gate lived in whichever script happened to call it, and a second path
around it was one script away.

**What a wrapper does now.** Refuse a dirty or unpushed tree (the preflight
above), resolve `git rev-parse HEAD`, then run its targets' triggers in order at
that commit -- streaming each build's log and stopping at the first failed
build. `scripts/deploy_build_targets.sh` holds that logic once: it reads each
build's FINAL STATUS from `gcloud builds describe` rather than trusting the log
reader's exit code, because "the log was read successfully" is not "the build
succeeded". Which targets each wrapper runs is tabulated in
[`../components/config-deployment.md`](../components/config-deployment.md).

`deploy-staging.sh` additionally runs the `verify` target FIRST when the commit
has no `build_checks` record yet, so a first deploy of a new commit is one
command rather than two -- and a second target for the same commit skips it,
which is the whole point of recording per SHA.

**Running a wrapper is still a maintainer-gated deploy.** Only the engine
changed: the per-instance permission ask in the two gate sections above applies
exactly as before.

The pieces:

- **`cloudbuild.yaml`** at the repo root, one build file selected by `_TARGET`
  (with `_CHANNEL` and `_SHA`). Every target the plan names is implemented;
  `landing` is declared as a step that fails with "target not implemented"
  rather than being absent, because a target matching no step would build
  nothing and report SUCCESS.
- **The verify gate.** `_TARGET=verify` runs the backend, frontend and
  admin-console suites ONCE for a SHA and writes `build_checks/{sha}`. Every
  deploy target's FIRST step requires that record and fails without it, so
  five targets for one commit pay one test run -- and a commit whose suites
  failed cannot be deployed by any route. It fails CLOSED: a Firestore read
  that errors refuses the deploy.
- **`deploy/channels/<channel>.env`**, the per-channel Cloud Run config as
  plain data. `cloudbuild.yaml` reads it by SOURCING `deploy-all.sh` and
  calling that file's own `read_channel_section` -- the one place where a
  wrapper is still load-bearing, and why `deploy-all.sh` keeps a helper half
  above its sourcing guard. See
  [`../components/config-deployment.md`](../components/config-deployment.md)
  for the format and the parity rule.
- **`scripts/setup-cloud-build.sh`**, the operator-run provisioning step that
  creates one manual trigger per target once the 2nd-generation GitHub
  connection exists (that connection is a one-time OAuth only the maintainer
  can do, and nothing deploys without it).
  It also provisions the build's OWN identity, `polyglot-cloudbuild-sa`
  (bd `polyglot-pdf-p4ale`, E4.5) -- a dedicated SA, never the legacy
  default Cloud Build SA, holding `run.admin`, `firebasehosting.admin`,
  `firebaserules.admin`, `artifactregistry.writer`, `logging.logWriter`,
  `datastore.user` and `datastore.indexAdmin` project-wide,
  `storage.objectAdmin` on the form-kits
  bucket only, and resource-scoped actAs (`roles/iam.serviceAccountUser`)
  on BOTH `polyglot-backend-sa` and `admin-backend-sa` -- deploying a
  revision that runs as a given SA is itself privileged on that SA, so the
  build needs this binding on each runtime identity it deploys as. The
  Pub/Sub service agent also gets `roles/iam.serviceAccountTokenCreator`
  here, for the OIDC token the build-status webhook needs.
  **`datastore.indexAdmin` is a NEW grant and the live SA does not hold it
  until this script is re-run** -- the `firestore-rules` target deploys the
  composite indexes as well as the rules, and neither `firebaserules.admin`
  (rules only) nor `datastore.user` (read only) covers an index write. Until
  the re-run, the first `firestore-rules` build fails `PERMISSION_DENIED`, and
  because `deploy-demo.sh` runs that target BEFORE `frontend-demo` it takes the
  frontend deploy down with it. Check the live grant without deploying:
  `gcloud projects get-iam-policy polyglot-demo-aa709
  --flatten='bindings[].members'
  --filter='bindings.members:polyglot-cloudbuild-sa@polyglot-demo-aa709.iam.gserviceaccount.com'
  --format='value(bindings.role)'`.
  `admin-backend-sa` gains the mirror grant -- actAs on
  `polyglot-cloudbuild-sa` ONLY -- so the admin service's trigger route can
  submit a build that runs as the build identity; see
  [`../components/admin-service.md`](../components/admin-service.md) and
  [`../components/config-deployment.md`](../components/config-deployment.md)
  for the full role tables and the two pinning test files
  (`admin_backend/tests/unit/test_cloud_build_sa_iam_envelope.py`,
  `tests/test_setup_cloud_build_script.py`).

## The staging-before-demo promotion gate

**This gate lives inside `cloudbuild.yaml`, and every deploy now runs through
it** (bd `polyglot-pdf-oqtm7`, E4.6 -- `deploy-demo.sh` is a thin trigger
wrapper, so there is no bash path around the gate left to take).

Every demo-family deploy --
`backend-demo`, `frontend-demo`, and the admin service's traffic shift --
requires a **successful staging deployment for the exact same target family
and commit SHA** before it may proceed. The rule lives in ONE pure predicate,
`admin_backend/services/promotion_gate.py::staging_verified(target_family,
sha, deployments)`, so the two places that enforce it can never disagree
about what "verified" means:

- **The build is the enforcement.** `cloudbuild.yaml`'s
  `staging-verified-gate` step (for `backend-demo`/`frontend-demo`) and
  `admin-service-staging-gate` step (for the admin service's traffic shift)
  each call the predicate through `scripts/promotion_gate.py`, a thin CLI
  that queries Firestore's `deployments` collection and translates the
  boolean into an exit code. This runs INSIDE the build, before the deploy
  step, so a bash-submitted build cannot bypass it any more than a
  console-triggered one can.
- **The route is a courtesy, not the enforcement.** `POST /admin/deploys`
  (`admin_backend/routes/deploy_routes.py`) calls the same predicate for
  `backend-demo` and `frontend-demo` BEFORE ever triggering a build, and
  returns an early 409 naming the missing family/sha combination rather
  than making the operator wait for a build to fail minutes in.
  - **The admin service is deliberately excluded from this early route
    check** (`deploy/targets.py`'s `GATED_TARGETS` names only
    `backend-demo`/`frontend-demo`). The admin service has no separate
    staging build of its own -- its tagged-candidate deploy and its
    traffic shift are two steps of the SAME Cloud Build run, and the
    staging-equivalent proof (`admin-service-record-deployment`) is
    written by an earlier step of that same build. A pre-build route
    check could therefore never find a row for a brand-new SHA and would
    refuse every admin-service deploy forever; its enforcement is
    in-build only. Pinned by
    `admin_backend/tests/unit/test_deploy_routes.py::
    test_admin_service_is_not_refused_by_the_early_gate`.
- **No recency rule -- a deliberate, maintainer-reversible decision** (the
  plan's own open question, "whether a recency rule is wanted on
  promotion", recommendation: none, taken here). An older SHA's staging
  success is never invalidated by a LATER staging deploy of a different
  SHA: promoting that older, already-verified commit to the demo (a
  rollback) must remain possible even after staging has since moved on.
  `staging_verified()` matches on exact (family, sha) alone -- there is no
  "is this the newest staging record" comparison anywhere in the rule.

Pinned by `admin_backend/tests/unit/test_promotion_gate.py` (the pure
predicate's exhaustive per-field table),
`admin_backend/tests/unit/test_demo_promotion_gate.py` (the route's both
directions through a real request, the case table the plan text names by
name, and the CLI's exit codes under a stubbed Firestore), and
`tests/test_cloudbuild_yaml.py` (every demo-side gate step actually
invokes `scripts/promotion_gate.py` with both the target-derived family
and the real `_SHA`, simulated at runtime rather than only substring-
matched).

## The admin tier: its own staging, not a third channel

The admin service (`admin_backend/`, Cloud Run `polyglot-admin`) and console
(`admin-console/`, Hosting) are a SEPARATE control plane from the two tiers
above -- they are not a "third channel" alongside staging and demo. There is
ONE admin service and ONE console backing BOTH staging's AND the demo's
data (the admin service has no channel of its own), so this tier needs a
staging mechanism of its own, shaped differently from the public app's
staging/demo split: a bad admin deploy would otherwise take the control
plane down for both channels at once, and there is no second Cloud Run
service to rehearse against first the way the public backend has staging.

- **Backend (the `admin-service` target, started by `deploy-admin.sh`):**
  every deploy lands as a Cloud Run
  revision with `--no-traffic --tag candidate`, is health-checked at ITS
  OWN stable tagged URL, and only on success receives traffic via
  `gcloud run services update-traffic --to-latest`. A failing health check
  fails that build step, so the traffic shift never runs and the
  previously-live revision keeps serving. This is that service's own staging
  tier, expressed as a tagged-revision gate rather than a second deployed
  service.
- **Console (the `admin-console-candidate` and `admin-console` targets,
  started by `deploy-admin-console.sh`):** a bare run deploys the
  permanent `polyglot-admin-candidate` Hosting site; a SEPARATE
  explicit run with `--live` deploys the same commit to
  `polyglot-admin-demo`, the site operators actually use. A fixed second
  site is used instead of a Hosting preview channel because a preview
  channel's random-hash URL would have to be re-added to Firebase Auth's
  authorized domains and to the admin service's CORS allowlist on every
  single deploy.
- **Gating:** the SAME three-part gate as the public app's demo/staging
  deploys above (local test first, explicit per-instance maintainer
  permission before each run, post-deploy test-drive) applies to both
  `deploy-admin.sh` and `deploy-admin-console.sh` -- neither is on any
  standing pre-authorization.

Full detail (routes, the service account's IAM envelope, the console's
pages, one-time per-project setup) is in
[`../components/admin-service.md`](../components/admin-service.md).

## Environment detection

Use ONE canonical signal for "which environment am I in" (e.g. a single
`IS_STAGING` / `APP_ENV` variable read through one helper), not ad-hoc hostname
or env-string checks scattered across the code. If the topology grows, migrate
the one helper; call sites keep working.

Note that today the two channels are distinguished by *deploy wiring* -- the
build's `_CHANNEL` substitution picks the Cloud Run service, the Hosting target
and the channel config file -- rather than by any runtime
flag. The staging backend runs a byte-identical config to the demo's, on
purpose, so staging predicts demo behavior. If a genuine runtime difference is
ever needed, add it through one helper as above.

## Channel specifics

Both channels live in project `polyglot-demo-aa709` (GCP + Firebase together).
`deploy-demo.sh` and `deploy-staging.sh` both check for the `caellwyn@gmail.com`
gcloud account and re-auth if needed.

| | staging | demo |
|---|---|---|
| script | `./deploy-staging.sh` | `./deploy-demo.sh` |
| URL | https://polyglot-app-staging.web.app | https://polyglot-demo-aa709.web.app |
| Cloud Run | `polyglot-backend-staging` | `polyglot-backend` |
| form kits (bare run or `--all`) | **skipped** (shared bucket) | **skipped** (shared bucket) |
| Firestore rules | never | deployed |
| channel config | `deploy/channels/staging.env` | `deploy/channels/demo.env` |
| Cloud Build targets | `verify` (when unrecorded), `backend-staging`, `frontend-staging` | `backend-demo`, `firestore-rules`, `frontend-demo` |
| `form-kits` target | only with `--form-kits` | only with `--form-kits` |

The backend runs on Cloud Run co-located with Gemini and NEVER logs full PII
bodies -- see [`../standards/hipaa-pii-policy.md`](../standards/hipaa-pii-policy.md).
The hosted schema editor is a third Hosting site (`polyglot-editor-demo`) and
ships via the `editor` target (`deploy-editor.sh`); it has no staging
counterpart.

_(Keep secrets out of this doc -- reference names, not values.)_
