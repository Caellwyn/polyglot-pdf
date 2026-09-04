---
date: 2026-09-04
bead: polyglot-pdf-3l2vp
title: "feat(deploy): 1.3 deploy-all.sh runtime APP_MODULE/GIT_SHA + tagged no-traffic admin deploy; deploy-admin.sh bridge"
sprint: 22
tags: [refactor, testing]
---

## Trigger

Sprint 22 admin-console program, Epic 1 (foundations), bead 1.3 (plan:
`docs/sprint_22_admin-console_plan.md`, "Admin service" -- SA + staging tier +
first deploy). Beads 1.1 (admin_backend package skeleton, the shared image's
runtime `APP_MODULE` CMD selector, `scripts/setup-admin-service.sh`) and 1.2
(`require_app_admin`, `GET /admin/whoami`, `scripts/bootstrap_admin_user.py`)
had already shipped; this bead's remaining scope was the DEPLOY side --
teaching `deploy-all.sh` to actually pass `APP_MODULE`/`GIT_SHA` at deploy
time, and building the admin service's own staging tier (a no-traffic tagged
Cloud Run revision, verified before it receives traffic) since there is ONE
admin service backing both channels' data and a bad deploy to it would take
the whole control plane down at once.

## What shipped

`deploy-all.sh`'s backend stage now computes `APP_MODULE="${APP_MODULE:-backend.main:app}"`
and `GIT_SHA=$(git -C "$SCRIPT_DIR" rev-parse HEAD)` and passes both as
RUNTIME env in `--set-env-vars` on every backend deploy (never a build arg --
`gcloud builds submit --tag` cannot pass one). A caller that sets nothing --
every existing channel -- gets the exact invocation it had before; GIT_SHA
feeds the eventual `GET /version` git-sha field (bead 1.6, deliberately not
touched here).

A new optional `BACKEND_NO_TRAFFIC_TAG` env var, when set, makes the same
stage deploy `--no-traffic --tag "$BACKEND_NO_TRAFFIC_TAG"` instead of
shifting traffic immediately. After the existing IAM reachability gate, it
builds the tag's own STABLE URL (gcloud composes it as
`https://<tag>---<service>-<hash>.a.run.app`; there is no `describe` query for
a revision-scoped address, so this is string-built from the service's base
URL), curls its `/health`, and only on a 200 response runs
`gcloud run services update-traffic --to-latest`. A non-200 (or a connection
failure, `curl`'s `000` sentinel) aborts the script with exit 1 WITHOUT
shifting traffic -- the previously-live revision keeps serving. Unset (every
channel except the new one below), this whole block is a no-op.

New `deploy-admin.sh` is the bridge that actually uses it: it sets
`BACKEND_SERVICE_NAME=polyglot-admin`,
`BACKEND_SERVICE_ACCOUNT=admin-backend-sa@<project>...`,
`APP_MODULE=admin_backend.main:app`, `CORS_EXTRA_ORIGINS` (both admin Hosting
sites -- `polyglot-admin-demo`/`-candidate`, bead 1.7's targets, listed ahead
of their existing since an operator can run this script before 1.7 lands --
plus both channels' app origins, since the main app's firm-manager
`/console/*` pages call this service too), and
`BACKEND_NO_TRAFFIC_TAG=candidate`, then calls `deploy-all.sh --backend`.
It deploys the admin BACKEND only; the console's own Vite app and its two
Hosting sites are bead 1.7's `deploy-admin-console.sh`.

**Fresh-eyes fix round (post cross-surface review).** The Opus outer review
found one blocker: `ADMIN_CORS_ORIGINS` listed the `.firebaseapp.com` alias
for both admin-console origins but NOT for the two app-channel origins
(`polyglot-app-staging` and `$PROJECT`) -- inconsistent within the same
variable, and a real CORS-rejection risk for any `/console/*` page served
from the `.firebaseapp.com` domain (every Firebase Hosting site answers on
both domains by default; `deploy-demo.sh`/`deploy-staging.sh` already list
both for their own `CORS_EXTRA_ORIGINS`). **Adopted**: added the two missing
`.firebaseapp.com` aliases to `deploy-admin.sh`, tightened the comment to
state the dual-domain convention explicitly, and added
`tests/test_deploy_admin_cors_origins.py` -- derives every origin's host from
the live `ADMIN_CORS_ORIGINS` string and asserts each has BOTH domains
present, so it pins the *property* (per CLAUDE.md's "enumerate the set"
doctrine) rather than re-asserting today's two missing entries. Mutation-
verified: reverting the fix on a scratch copy reddened exactly
`test_every_origin_has_both_firebase_hosting_domains` naming the two
regressed hosts. **Rejected/deferred**: none -- the review's other two notes
(the tag-URL naming convention being unverified against a real deploy; the
region hardcoded rather than reading `deploy-all.sh`'s `$REGION`) were
explicitly not findings (PENDING-DEPLOY carve-out; matches an existing
duplicated literal, out of scope for this bead) and needed no action.

**Cross-surface fix round 2 (Dockerfile/`/health` staleness).** A second Opus
outer review found two GAPS on the same underlying shape -- a claim going
stale because the fact it described moved, not because the claim's own text
changed. **Adopted (F1)**: `Dockerfile`'s admin-package comment still said
"the admin service is not deployed yet and no deploy script sets APP_MODULE",
which this bead's `deploy-all.sh`/`deploy-admin.sh` changes made false; three
of the four `_PRODUCER_CLAIM_SITES` pinned by `tests/test_dockerfile_app_module.py`
had been updated to name the real producer but the Dockerfile's own comment
(phrased differently from the test's two exact-literal staleness strings,
"NONE YET"/"NOTHING SETS IT YET") slipped through. Corrected the comment to
name `deploy-all.sh`/`deploy-admin.sh` as the producers while still stating
plainly that the admin Cloud Run service itself has not been deployed
(maintainer-gated, separate step) -- and broadened the test's staleness
detector from the two exact literals to a claim-shaped regex (matches "no ...
sets/passes APP_MODULE" and "not deployed yet" however phrased) so a future
site describing the same "no producer yet" fact in yet another wording cannot
repeat the same escape. Mutation-verified: reverting the Dockerfile comment to
its stale wording reddens `test_docs_do_not_claim_a_live_app_module_producer_while_none_exists`
naming `Dockerfile` as the offending site. **Adopted (F2)**: four sites
(`docs/technical_guide.md`, `docs/components/config-deployment.md`,
`admin_backend/main.py`, `admin_backend/tests/unit/test_admin_health.py`)
asserted `/health` has "no deploy-time behavioral coverage" / "issues no HTTP
request" -- true of `verify_service_publicly_reachable()`'s IAM check, but
this bead's tagged no-traffic flow (`deploy-all.sh` curling the tag URL's
`/health` before `update-traffic --to-latest`) made the broader claim false
for the admin service's own deploy path specifically. Corrected all four to
state the narrower, still-true fact (the IAM check alone issues no HTTP
request) alongside the now-true one (the tagged flow does, and gates traffic
on it) -- `config-deployment.md` was the sharpest case, contradicting itself
seventeen lines apart against a paragraph this same bead had already added.
**Filed, not fixed (F3, F4)**: `polyglot-pdf-okfjn` (`deploy-admin.sh` has no
argument parser, so a typo like `--frontend` silently runs the full privileged
deploy instead of erroring -- the existing guard test is parametrized on a
hand-listed script set that should be derived, per scar #8) and
`polyglot-pdf-gdpku` (the "never serves a single request" comments on the
tagged no-traffic flow don't hold on a service's FIRST deploy, which is the
deploy `deploy-admin.sh` exists to perform -- `--no-traffic` has nothing to
reassign traffic FROM when there is no prior revision, so the first revision
takes 100% regardless; harmless in practice since verification still runs,
just after the revision is live rather than before). Both are documentation/
robustness nits with no correctness impact on this bead's exit criteria;
reasoned from `gcloud run deploy --help`'s documented behavior rather than
verified against live Cloud Run (a maintainer-gated deploy).

## Lessons

`tests/test_dockerfile_app_module.py` (shipped in bead 1.1) already had a
test asserting the docs' "NONE YET" producer claim stays in agreement with
whether a deploy script actually sets `APP_MODULE` -- so the moment this
bead's `deploy-all.sh` change landed, that test correctly went red until
`docs/technical_guide.md` and `admin_backend/__init__.py` were updated to
name the real producer in present tense. Worth calling out because it is the
doc-freshness discipline (CLAUDE.md's "docs are current-state only") enforced
mechanically rather than by review discovery -- exactly the intended effect.

`tests/test_deploy_channel_parity.py`'s `CHANNEL_SPECIFIC` allowlist gaining
`GIT_SHA` (named explicitly in the bead) turned out to be a no-op against the
CURRENT scripts: `GIT_SHA` lands in `deploy-all.sh`'s base `BACKEND_ENV`
string, never in a channel's own `BACKEND_EXTRA_ENV`, so the parity test's
parser (which only reads `BACKEND_EXTRA_ENV`) never sees it. Added anyway,
documented as currently inert, because a deployed commit is by nature never
supposed to compare equal across channels deployed at different times --
exactly the shape the allowlist exists to permit -- so a future channel
script that pins an explicit `GIT_SHA` must not be flagged as drift.

## Doc freshness

- `docs/technical_guide.md` section 12 (`APP_MODULE`): flipped "Producer:
  NONE YET" to name `deploy-all.sh`'s backend stage and `deploy-admin.sh`;
  added the tagged no-traffic staging-tier paragraph; extended the "Pinned
  by" list with the new test file. (No stamp bump -- tier-1, no-stamp by
  design.)
- `docs/components/config-deployment.md`: Tracks line gains `deploy-admin.sh`;
  new paragraph documenting the tag-URL health probe and traffic-shift gate,
  and what the script deliberately does not do; Last updated bumped to
  2026-09-04.
- `admin_backend/__init__.py` module docstring: flipped "NOTHING SETS THAT
  VARIABLE YET" to describe the real producer and the admin service's
  staging tier.
- Other stale docs flagged by `scripts/check_doc_freshness.py`
  (`schema-key-visibility.md`, `section-reset-deprecation.md`,
  `si-reduction.md`, `stateless-architecture.md`, `terminology.md`,
  `testing.md`, `validation-delegation.md`, `voice-and-vad.md`,
  `ws-protocol.md`) all track files unrelated to this bead's surfaces and
  were left as-is; the checker exits 0 (warn-only) and none of the listed
  files were touched here.

## Files touched

- `deploy-all.sh` -- runtime `APP_MODULE`/`GIT_SHA` env; `BACKEND_NO_TRAFFIC_TAG`
  gated tagged no-traffic deploy + tag-URL health probe + traffic shift.
- `deploy-admin.sh` (new) -- the admin backend's deploy bridge.
- `tests/test_deploy_admin_tag_flow.py` (new) -- executes the extracted
  backend-stage block against stubbed gcloud/curl/git; pins both the
  untagged (unchanged) and tagged (gated traffic shift) paths.
- `tests/test_deploy_admin_cors_origins.py` (new, fresh-eyes fix round) --
  pins that every `ADMIN_CORS_ORIGINS` host is listed on both
  `.web.app`/`.firebaseapp.com`.
- `tests/test_deploy_channel_parity.py` -- `CHANNEL_SPECIFIC` gains `GIT_SHA`.
- `docs/technical_guide.md`, `docs/components/config-deployment.md`,
  `admin_backend/__init__.py` -- doc updates above.

Review outcomes recorded in the closeout ping.
