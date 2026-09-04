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
- `tests/test_deploy_channel_parity.py` -- `CHANNEL_SPECIFIC` gains `GIT_SHA`.
- `docs/technical_guide.md`, `docs/components/config-deployment.md`,
  `admin_backend/__init__.py` -- doc updates above.

Review outcomes recorded in the closeout ping.
