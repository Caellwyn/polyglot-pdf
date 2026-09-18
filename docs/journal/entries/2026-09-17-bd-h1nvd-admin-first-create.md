---
date: 2026-09-17
bead: polyglot-pdf-h1nvd
title: "fix(deploy): deploy-admin.sh cannot create the admin service -- --no-traffic is refused on a first deploy"
sprint: 22
tags: [hotfix, testing]
---

## Trigger

Found 2026-09-14 on the admin service's first real deploy (sprint 23
unblock, a PR #775 follow-up): `deploy-admin.sh` always deploys
`polyglot-admin` as a `--no-traffic --tag candidate` revision, and Cloud Run
refuses that flag combination when the service does not exist yet
("--no-traffic not supported when creating a new service"). The image had
already been built and pushed by the time the deploy call failed, so the
failure landed minutes in, after the expensive step. This bead's exit
criteria: the first deploy creates the service without `--no-traffic`, a
second run keeps the tagged-candidate flow, and both branches are pinned by
tests that were red before the fix.

## What shipped

The bead was filed against `deploy-all.sh` / `deploy-admin.sh` doing the
`gcloud run deploy`, but bd `polyglot-pdf-oqtm7` ("thin Cloud Build
wrappers for all deploy scripts") landed on 2026-09-16 -- two days after
this bead was filed -- and moved every real `gcloud run deploy` call out of
bash and into `cloudbuild.yaml`. `deploy-all.sh` no longer deploys anything,
and `tests/test_deploy_admin_tag_flow.py` (the test file this bead's
surfaces named) had already been deleted; only a stale `.pyc` remained. The
actual bug now lives in `cloudbuild.yaml`'s `admin-service-deploy-tagged`
step, which still passed `--no-traffic --tag candidate` unconditionally.

The fix: `admin-service-deploy-tagged` already resolves
`ADMIN_SERVICE_URL` via a `gcloud run services describe ... 2>/dev/null ||
true` lookup, for its own env block (Surface contract 12). An empty result
from that same lookup now also means "the service does not exist yet", and
the `gcloud run deploy` call assembles its no-traffic/tag flags into a
`NO_TRAFFIC_FLAG` array that is empty on a first deploy. A first-deploy
revision therefore lands with 100% traffic immediately -- there is no
previous revision for a tag to protect traffic from. Every later run finds
`ADMIN_SERVICE_URL` non-empty and keeps the existing tagged flow untouched.

`admin-service-verify-tagged` needed the matching branch: it previously
always built a `candidate---<host>` URL and health-checked it. On a first
deploy no `candidate` tag was ever attached, so that URL would probe
something Cloud Run never created. It now checks the service's current
traffic allocation for a `candidate` tag (`status.traffic[].tag`) and
health-checks the base URL directly when none exists. This half was not
named in the bead's exit criteria, but leaving it unfixed would have meant
the "fixed" first deploy still failed one step later in the same build --
fixing only the create call would not have produced a working first deploy
end to end.

`deploy-admin.sh`'s header gained a paragraph naming the first-deploy
branch (exit criterion 2).

Two new tests in `tests/test_cloudbuild_yaml.py` stub `gcloud run services
describe polyglot-admin` to fail (first deploy) or succeed (existing
service) and capture the real `gcloud run deploy` argv, pinning that
`--no-traffic`/`--tag` are absent in the first case and present in the
second. A third test pins that `admin-service-verify-tagged` inspects
`status.traffic[].tag` rather than assuming a tag exists. All three were
confirmed red against the pre-fix `cloudbuild.yaml` (reverted, re-run,
restored) before being trusted.

## Deferred (not this bead)

`docs/components/admin-service.md` and `docs/components/config-deployment.md`
both restate the old, unconditional "always tagged no-traffic" description
and are named in this bead's own declared surfaces. Both files were mid-
flight under a separate claim, bd `polyglot-pdf-e1l5f` (a stacked-stamp-
collapse pass touching exactly those two files), which this session's
collision guard correctly refused to let this bead write alongside. That
claim's own branch (`docs/e1l5f-topup-docs-nit`) turned out to already carry
a finished, unmerged commit set (including its own closeout journal entry)
-- so the work exists, just not yet landed. Rather than force past the
guard or duplicate that work, this bead updated `docs/technical_guide.md`
(not one of e1l5f's surfaces) instead, and leaves the two component docs to
whichever session lands e1l5f next; that session's own doc pass should pick
up the current-state fact this bead adds.

## Lessons

A bead's declared `surfaces` metadata is a snapshot at filing time, not a
live pointer -- a bug filed against a bash script can have its real fix
site moved out from under it by an unrelated, later-landing epic bead in
the same sprint. Before touching a bead's declared surfaces, re-derive
where the behavior actually lives today (`git log` on the named files, a
search for the described error string) rather than trusting the bead body.

`bd_safe.py claim`'s change-surface collision guard is a hard block by
design and was not bypassed for the genuine overlap (`config-deployment.md`)
-- only `--no-surface-check`'s SAME-BEAD false positive (this bead's own
freshly-created worktree branch, checked from the wrong shell cwd) was
worked around, after confirming from the colliding branch's own commit log
that its work was complete and unmerged, not actively in flight.

## Doc freshness

- `docs/technical_guide.md`: Surface contract 12's "Staging tier" bullet
  updated with the first-deploy branch (no stamp -- this doc has none by
  design).
- `docs/components/admin-service.md` / `docs/components/config-deployment.md`:
  reviewed, found stale on this exact point, left as-is -- both are
  declared surfaces of a separate, already-complete unmerged claim
  (bd `polyglot-pdf-e1l5f`); see "Deferred" above.
- `scripts/check_doc_freshness.py` run: reports pre-existing STALE entries
  unrelated to this bead's changes (warn-only, exit 0); `docs/technical_guide.md`
  itself reports OK.

## Files touched

- `cloudbuild.yaml` -- `admin-service-deploy-tagged` first-deploy branch;
  `admin-service-verify-tagged` candidate-tag detection.
- `deploy-admin.sh` -- header paragraph describing the first-deploy branch.
- `tests/test_cloudbuild_yaml.py` -- three new tests pinning both branches
  of the deploy step and the verify step's tag detection.
- `docs/technical_guide.md` -- Surface contract 12 updated with the
  first-deploy branch.
- `docs/journal/entries/2026-09-17-bd-h1nvd-admin-first-create.md` -- this
  entry.

Review outcomes recorded in the closeout ping.
