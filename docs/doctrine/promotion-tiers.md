# Promotion-tiers doctrine: worktree -> local -> dev -> staging -> demo

*Last updated: 2026-09-08 (bd polyglot-pdf-jecrl: firm-billing isolation between staging and the demo no longer rests on staging using its own mock firm -- the mint route refuses a live (or kindless) firm unless the raw `LINK_CHANNEL` is exactly `demo`, and a credit is reserved before any token is signed.) (bd polyglot-pdf-2cwja: added the admin-tier row -- the admin service and console's OWN tagged-revision + candidate-site staging, distinct from the public app's staging/demo split above. No code changed in this bead.) (bd polyglot-pdf-t7drr: recorded the shared-surface decisions for LINK_TOKEN_SECRET and the form-kit editing lock -- both shared on purpose. Earlier the same day, bd polyglot-pdf-3q9qn: client links are isolated per channel -- every token names the channel that may open it and each channel keeps its own redemption ledger, so a staging link no longer opens or burns on the demo.)*

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
   in the **demo's** form list. `deploy-staging.sh` therefore does **not** deploy
   form kits on a bare run -- pass `--form-kits` only when you mean to publish.
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

   **`LINK_TOKEN_SECRET` is deliberately the SAME on both channels.** Each
   deploy script binds the identical Secret Manager secret
   (`BACKEND_SECRETS_COMMON`), and that is the intended choice, not an
   oversight: the signing key is not what separates the channels -- the `aud`
   claim is, and it is checked on every redemption regardless of who signed the
   token. Giving each channel its own key would add nothing (a cross-channel
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

`deploy-all.sh` now **aborts** rather than reporting success in that case (bd
`polyglot-pdf-pidtg`). If it fires:

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

`deploy-demo.sh` deploys BOTH the frontend (Firebase Hosting) and backend
(Cloud Run) to the demo project `polyglot-demo-aa709`. The agent is authorized to
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

`deploy-staging.sh` deploys the frontend and backend to the staging site/service
inside the same project. It is **gated the same way as the demo deploy** (local
test -> explicit per-instance permission -> post-deploy test-drive).

> **Open question for the maintainer, deliberately NOT decided here.** Staging is
> disposable and nobody is watching it, so a per-instance ping before each
> staging deploy may be more friction than it is worth -- arguably staging should
> be standing-authorized like the local stack, leaving the per-instance ask for
> the demo only. That is an autonomy-boundary change (a step-2 call), so it stays
> gated until the maintainer says otherwise. It is NOT a licence for the agent to
> widen it unilaterally.

Two things are gated MORE tightly than the channel itself, because they cross the
staging/demo boundary (see "What is separate, and what is NOT"):

- **`deploy-staging.sh --form-kits`** publishes to the SHARED bucket and changes
  the DEMO's form list. Treat it as a demo action, not a staging one.
- **Firestore rules** are project-wide; `deploy-staging.sh` does not deploy them
  at all. A rules change ships deliberately via `deploy-demo.sh`.

`deploy-production.sh` targets a DEAD, unreachable project (`polyglot-forms-919f2`,
bd `polyglot-pdf-je6iy`) and now **refuses to run**, printing a pointer to the two
live channels. Reviving a real prod channel is a maintainer decision requiring a
reachable project, a full `scripts/setup-gcp-project.sh` bootstrap, real
`VITE_FIREBASE_*` values in `.env.production`, and its own Auth user set.

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

- **Backend (`deploy-admin.sh`):** every deploy lands as a Cloud Run
  revision with `--no-traffic --tag candidate`, is health-checked at ITS
  OWN stable tagged URL, and only on success receives traffic via
  `gcloud run services update-traffic --to-latest`. A failing health check
  aborts before any traffic shifts, so the previously-live revision keeps
  serving. This is that service's own staging tier, expressed as a
  tagged-revision gate rather than a second deployed service.
- **Console (`deploy-admin-console.sh`):** every deploy lands on the
  permanent `polyglot-admin-candidate` Hosting site first; a SEPARATE
  explicit run with `--live` promotes the same build to
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

Note that today the two channels are distinguished by *deploy wiring*
(`BACKEND_SERVICE_NAME`, `FRONTEND_HOSTING_TARGET`) rather than by any runtime
flag -- the staging backend runs a byte-identical config to the demo's, on
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
| form kits on bare run | **skipped** (shared bucket) | deployed |
| Firestore rules | never | deployed |

The backend runs on Cloud Run co-located with Gemini and NEVER logs full PII
bodies -- see [`../standards/hipaa-pii-policy.md`](../standards/hipaa-pii-policy.md).
The hosted schema editor is a third Hosting site (`polyglot-editor-demo`) and
ships via `deploy-editor.sh`; it has no staging counterpart.

_(Keep secrets out of this doc -- reference names, not values.)_
